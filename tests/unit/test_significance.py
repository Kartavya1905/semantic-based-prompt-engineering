"""
FILE:         tests/unit/test_significance.py
WHAT IT DOES: Checks the Phase 7 statistics on hand-built data whose right answers are known:
              bootstrap intervals, paired McNemar comparisons, Holm correction, calibration,
              seed consistency, and the report tool end to end (with the oracle fake model).
WHERE IT FITS: Phase 7.
"""

import json

import numpy as np
import pandas as pd
import pytest

from evaluation.analyze_results import build_report, load_analysis_frame, run_comparisons
from evaluation.experiment_config import ExperimentConfig
from evaluation.golden_case_model import load_golden_cases
from evaluation.run_benchmark import run_experiment
from evaluation.significance import (
    apply_holm_correction,
    bootstrap_mean_ci,
    calibration,
    compare_paired,
    per_case_scores,
    seed_consistency,
)
from prompt_engine.settings import PROJECT_ROOT
from tests.fakes import OracleLLMClient

DATASET_PATH = PROJECT_ROOT / "evaluation" / "golden_datasets" / "ticket_triage" / "v2.jsonl"


def case_frame(scores_by_case: dict[str, list[float]], metric: str = "correct") -> pd.DataFrame:
    """One row per run; a case with several scores = several seeds of the same ticket."""
    return pd.DataFrame([
        {"case_id": case_id, metric: score}
        for case_id, scores in scores_by_case.items() for score in scores
    ])


# --- 1. Bootstrap intervals --------------------------------------------------------------------
def test_interval_contains_the_mean_and_is_reproducible():
    case_scores = np.array([1.0] * 30 + [0.0] * 10)
    low, high = bootstrap_mean_ci(case_scores)
    assert low < case_scores.mean() < high
    assert bootstrap_mean_ci(case_scores) == (low, high)  # fixed rng seed


def test_more_tickets_give_a_narrower_interval():
    small_low, small_high = bootstrap_mean_ci(np.array([1.0, 0.0] * 10))
    large_low, large_high = bootstrap_mean_ci(np.array([1.0, 0.0] * 200))
    assert (large_high - large_low) < (small_high - small_low)


def test_constant_scores_give_a_zero_width_interval():
    assert bootstrap_mean_ci(np.ones(12)) == (1.0, 1.0)


def test_repeated_runs_of_one_ticket_count_once():
    frame = case_frame({"TT-1": [1, 1, 0], "TT-2": [0, 0, 0]})
    assert per_case_scores(frame, "correct").to_dict() == pytest.approx({"TT-1": 2 / 3, "TT-2": 0})


# --- 2. Paired comparisons ---------------------------------------------------------------------
LABELS = ("test-model T=0.0", "baseline@1", "candidate@1")


def test_identical_variants_show_no_difference():
    frame = case_frame({f"TT-{i}": [i % 2] for i in range(20)})
    comparison = compare_paired(frame, frame, "correct", LABELS)
    assert comparison.difference == 0
    assert (comparison.only_baseline_right, comparison.only_candidate_right) == (0, 0)
    assert comparison.mcnemar_p == 1.0
    assert comparison.verdict == "no detectable difference"


def test_three_fixed_tickets_are_not_yet_significant():
    """The llama v3→v5 critical result: 3 tickets fixed, none broken → p = 0.25."""
    baseline = case_frame({f"TT-{i}": [0 if i < 3 else 1] for i in range(5)})
    candidate = case_frame({f"TT-{i}": [1] for i in range(5)})
    comparison = compare_paired(baseline, candidate, "correct", LABELS)
    assert (comparison.only_baseline_right, comparison.only_candidate_right) == (0, 3)
    assert comparison.mcnemar_p == pytest.approx(0.25)
    assert comparison.verdict == "no detectable difference"


def test_ten_fixed_tickets_are_significant():
    baseline = case_frame({f"TT-{i}": [0 if i < 10 else 1] for i in range(30)})
    candidate = case_frame({f"TT-{i}": [1] for i in range(30)})
    comparison = compare_paired(baseline, candidate, "correct", LABELS)
    assert comparison.mcnemar_p == pytest.approx(2 * 0.5 ** 10)
    assert comparison.difference == pytest.approx(10 / 30)
    assert comparison.difference_ci[0] > 0
    assert comparison.verdict == "better"


def test_only_shared_tickets_are_compared():
    baseline = case_frame({"TT-1": [1], "TT-2": [0], "TT-3": [1]})
    candidate = case_frame({"TT-2": [1], "TT-3": [1], "TT-4": [0]})
    assert compare_paired(baseline, candidate, "correct", LABELS).case_count == 2


def test_no_shared_tickets_is_an_error():
    with pytest.raises(ValueError, match="share no tickets"):
        compare_paired(case_frame({"TT-1": [1]}), case_frame({"TT-2": [1]}), "correct", LABELS)


def test_holm_correction_adjusts_for_several_tests():
    comparisons = []
    for raw_p in (0.01, 0.04, 0.5):
        one_ticket = case_frame({"TT-1": [1]})
        comparison = compare_paired(one_ticket, one_ticket, "correct", LABELS)
        comparison.mcnemar_p = raw_p
        comparisons.append(comparison)
    apply_holm_correction(comparisons)
    assert [comparison.holm_p for comparison in comparisons] == pytest.approx([0.03, 0.08, 0.5])


# --- 3. Calibration and consistency -------------------------------------------------------------
def test_well_calibrated_confidence_has_near_zero_error():
    confidences = np.full(100, 0.9)
    outcomes = np.array([1] * 90 + [0] * 10)
    result = calibration(confidences, outcomes)
    assert result.expected_calibration_error == pytest.approx(0.0)
    assert result.accuracy == pytest.approx(0.9)


def test_overconfidence_is_measured():
    result = calibration(np.ones(10), np.array([1, 0] * 5))
    assert result.expected_calibration_error == pytest.approx(0.5)
    assert result.brier_score == pytest.approx(0.5)


def test_seed_consistency():
    frame = pd.DataFrame({
        "case_id": ["TT-1"] * 3 + ["TT-2"] * 3,
        "predicted_category": ["billing"] * 3 + ["technical", "technical", "account"],
        "predicted_urgency": ["high"] * 6,
        "predicted_escalation": [False] * 6,
    })
    assert seed_consistency(frame) == pytest.approx((1 + 2 / 3) / 2)


# --- 4. The report tool on real result files (written by the oracle fake model) ---------------
@pytest.fixture(scope="module")
def oracle_results_path(tmp_path_factory):
    import asyncio

    answers_by_body = {
        case.input_variables["ticket_body"]: case.expected_output | {
            "summary": case.reference_summary, "confidence_score": 0.9,
        }
        for case in load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    }
    config = ExperimentConfig.model_validate({
        "experiment_id": "oracle_analysis", "description": "Oracle results for report tests.",
        "prompt_id": "ticket_triage", "prompt_versions": ["v1_baseline", "v3_fewshot"],
        "model_names": ["oracle"], "temperatures": [0.0, 0.7], "seeds": [1, 2],
        "dataset_path": str(DATASET_PATH), "dataset_split": "dev", "required_tag": "smoke",
        "compute_summary_similarity": False,
    })
    results_dir = tmp_path_factory.mktemp("results")
    return asyncio.run(run_experiment(
        config, lambda model_name: OracleLLMClient(answers_by_body, model_name=model_name),
        results_dir=results_dir,
    ))


def test_report_compares_two_perfect_variants(oracle_results_path):
    frame = load_analysis_frame([oracle_results_path])
    comparisons = run_comparisons(frame, [("v1_baseline@1.0.0", "v3_fewshot@1.0.0")])
    assert len(comparisons) == 2 * 3  # 2 temperatures × 3 comparison targets
    assert all(comparison.verdict == "no detectable difference" for comparison in comparisons)

    report_text = build_report(frame, comparisons, [oracle_results_path])
    for heading in ("## 1. Leaderboard", "## 2. Paired comparisons", "## 3. Calibration",
                    "## 4. Seed consistency"):
        assert heading in report_text


def test_unknown_variant_is_reported_clearly(oracle_results_path):
    frame = load_analysis_frame([oracle_results_path])
    with pytest.raises(ValueError, match="v9_missing@1.0.0 not found"):
        run_comparisons(frame, [("v1_baseline@1.0.0", "v9_missing@1.0.0")])


def test_results_from_different_answer_keys_are_refused(oracle_results_path, tmp_path):
    other_key_path = tmp_path / "other_key.jsonl"
    rows = [json.loads(line) for line in oracle_results_path.read_text("utf-8").splitlines()]
    other_key_path.write_text(
        "\n".join(json.dumps(row | {"dataset_sha256": "0123456789ab",
                                    "run_key": row["run_key"] + "|other"}) for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different answer keys"):
        load_analysis_frame([oracle_results_path, other_key_path])


# --- 5. Power ----------------------------------------------------------------------------------
def test_detectable_difference_shrinks_with_more_tickets():
    from evaluation.significance import minimum_detectable_difference

    small = minimum_detectable_difference(case_count=36, disagreement_count=10)
    large = minimum_detectable_difference(case_count=360, disagreement_count=100)
    assert small == pytest.approx(2.8 * np.sqrt((10 / 36) / 36))
    assert large < small
    assert minimum_detectable_difference(case_count=36, disagreement_count=0) is None


def test_tickets_needed_for_a_ten_point_gain():
    from evaluation.significance import tickets_needed

    # With ~28% of tickets answered differently by the two variants (as observed on dev),
    # confirming a 10-point improvement needs roughly 220 paired tickets.
    assert 200 <= tickets_needed(target_difference=0.10, disagreement_rate=0.28) <= 240
