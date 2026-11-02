"""
FILE:         evaluation/significance.py
WHAT IT DOES: The statistics that separate real improvements from luck:
              - cluster bootstrap confidence intervals (resampling TICKETS, not rows)
              - paired comparisons of two prompt variants on the same tickets
                (bootstrap CI of the difference + exact McNemar test)
              - Holm correction when many comparisons are made at once
              - calibration of the model's confidence_score (ECE, Brier score)
              - consistency of answers across random seeds
WHERE IT FITS: Phase 7. Pure functions on result DataFrames; analyze_results.py builds the report.
WHY CLUSTERS: one ticket run at 4 temperatures × 3 seeds is still ONE ticket. Treating its 10 rows
              as 10 independent samples would make every interval look far too confident.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

DEFAULT_RESAMPLES = 10_000
CONFIDENCE_LEVEL = 0.95


# --- 1. One score per ticket: average a metric over all rows of the same case -------------------
def per_case_scores(frame: pd.DataFrame, metric: str) -> pd.Series:
    return frame.groupby("case_id")[metric].mean().astype(float)


# --- 2. Cluster bootstrap CI: resample tickets with replacement, recompute the mean -------------
def bootstrap_mean_ci(
    case_scores: np.ndarray, resamples: int = DEFAULT_RESAMPLES, rng_seed: int = 0
) -> tuple[float, float]:
    if len(case_scores) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(rng_seed)
    sample_indices = rng.integers(0, len(case_scores), size=(resamples, len(case_scores)))
    resampled_means = case_scores[sample_indices].mean(axis=1)
    tail = (1 - CONFIDENCE_LEVEL) / 2
    low, high = np.quantile(resampled_means, [tail, 1 - tail])
    return float(low), float(high)


# --- 3. Paired comparison: same tickets, two variants -------------------------------------------
@dataclass
class PairedComparison:
    condition: str           # e.g. "qwen2.5:7b T=0.0 constrained"
    metric: str
    baseline: str
    candidate: str
    case_count: int
    baseline_mean: float
    candidate_mean: float
    difference: float        # candidate - baseline
    difference_ci: tuple[float, float]
    only_baseline_right: int  # McNemar "b": tickets the candidate broke
    only_candidate_right: int  # McNemar "c": tickets the candidate fixed
    mcnemar_p: float
    holm_p: float | None = None

    @property
    def verdict(self) -> str:
        p_value = self.holm_p if self.holm_p is not None else self.mcnemar_p
        if p_value < 0.05:
            return "better" if self.difference > 0 else "worse"
        return "no detectable difference"


def compare_paired(
    baseline_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    metric: str,
    labels: tuple[str, str, str],
    resamples: int = DEFAULT_RESAMPLES,
    rng_seed: int = 0,
) -> PairedComparison:
    """labels = (condition, baseline name, candidate name). Only shared tickets are compared."""
    condition, baseline_name, candidate_name = labels
    aligned = pd.concat(
        [per_case_scores(baseline_frame, metric).rename("baseline"),
         per_case_scores(candidate_frame, metric).rename("candidate")],
        axis=1, join="inner",
    )
    if aligned.empty:
        raise ValueError(f"{baseline_name} and {candidate_name} share no tickets")

    # 3a. Bootstrap the per-ticket DIFFERENCE: pairing removes ticket difficulty from the noise.
    per_case_difference = (aligned["candidate"] - aligned["baseline"]).to_numpy()
    difference_ci = bootstrap_mean_ci(per_case_difference, resamples, rng_seed)

    # 3b. Exact McNemar on "mostly right" per ticket: only tickets where the variants DISAGREE
    # carry information. b = fixed→broken, c = broken→fixed.
    baseline_right = aligned["baseline"] >= 0.5
    candidate_right = aligned["candidate"] >= 0.5
    only_baseline_right = int((baseline_right & ~candidate_right).sum())
    only_candidate_right = int((~baseline_right & candidate_right).sum())
    mcnemar_p = 1.0 if only_baseline_right + only_candidate_right == 0 else float(
        mcnemar([[0, only_baseline_right], [only_candidate_right, 0]], exact=True).pvalue
    )

    return PairedComparison(
        condition=condition, metric=metric, baseline=baseline_name, candidate=candidate_name,
        case_count=len(aligned),
        baseline_mean=float(aligned["baseline"].mean()),
        candidate_mean=float(aligned["candidate"].mean()),
        difference=float(per_case_difference.mean()),
        difference_ci=difference_ci,
        only_baseline_right=only_baseline_right,
        only_candidate_right=only_candidate_right,
        mcnemar_p=mcnemar_p,
    )


# --- 3c. Power: the smallest difference a paired test on these tickets would reliably detect ---
# Normal approximation for McNemar at alpha=0.05 (two-sided) and 80% power:
#   detectable difference ≈ (1.96 + 0.84) * sqrt(disagreement_rate / tickets)
# A result of "no detectable difference" below this size means "not measurable here", not "none".
def minimum_detectable_difference(case_count: int, disagreement_count: int) -> float | None:
    if case_count == 0 or disagreement_count == 0:
        return None
    return float((1.96 + 0.84) * np.sqrt((disagreement_count / case_count) / case_count))


def tickets_needed(target_difference: float, disagreement_rate: float) -> int:
    """Paired tickets needed to detect target_difference with 80% power (alpha 0.05)."""
    numerator = (
        1.96 * np.sqrt(disagreement_rate)
        + 0.84 * np.sqrt(disagreement_rate - target_difference ** 2)
    ) ** 2
    return int(np.ceil(numerator / target_difference ** 2))


# --- 4. Many comparisons at once → some "significant" by luck. Holm controls that. ------------
def apply_holm_correction(comparisons: list[PairedComparison]) -> None:
    if not comparisons:
        return
    _, holm_p_values, _, _ = multipletests(
        [comparison.mcnemar_p for comparison in comparisons], method="holm"
    )
    for comparison, holm_p in zip(comparisons, holm_p_values, strict=True):
        comparison.holm_p = float(holm_p)


# --- 5. Calibration: when the model says 0.9 confident, is it right 90% of the time? -----------
@dataclass(frozen=True)
class CalibrationResult:
    answer_count: int
    mean_confidence: float
    accuracy: float
    expected_calibration_error: float  # 0 = perfectly calibrated
    brier_score: float                 # mean squared error of the confidence; lower is better


def calibration(
    confidences: np.ndarray, outcomes: np.ndarray, bin_count: int = 5
) -> CalibrationResult:
    """confidence_score is defined as P(category AND urgency correct), so outcomes must match."""
    confidences, outcomes = confidences.astype(float), outcomes.astype(float)
    bin_edges = np.linspace(0.0, 1.0, bin_count + 1)
    bin_ids = np.clip(np.digitize(confidences, bin_edges[1:-1]), 0, bin_count - 1)
    calibration_error = sum(
        (bin_ids == bin_id).mean()
        * abs(confidences[bin_ids == bin_id].mean() - outcomes[bin_ids == bin_id].mean())
        for bin_id in range(bin_count) if (bin_ids == bin_id).any()
    )
    return CalibrationResult(
        answer_count=len(confidences),
        mean_confidence=float(confidences.mean()),
        accuracy=float(outcomes.mean()),
        expected_calibration_error=float(calibration_error),
        brier_score=float(((confidences - outcomes) ** 2).mean()),
    )


# --- 6. Seed consistency: does the same ticket get the same answer on every seed? -------------
def seed_consistency(frame: pd.DataFrame) -> float:
    """Mean over tickets of the share of runs agreeing with that ticket's most common answer."""
    answer_signature = (
        frame["predicted_category"].astype(str) + "|" + frame["predicted_urgency"].astype(str)
        + "|" + frame["predicted_escalation"].astype(str)
    )
    agreement_per_case = answer_signature.groupby(frame["case_id"]).agg(
        lambda answers: answers.value_counts().iloc[0] / len(answers)
    )
    return float(agreement_per_case.mean())
