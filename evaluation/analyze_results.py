"""
FILE:         evaluation/analyze_results.py
WHAT IT DOES: Turns benchmark result files into a statistical report (Markdown):
              1. leaderboard with 95% confidence intervals (cluster bootstrap over tickets)
              2. paired comparisons you ask for: difference, its 95% CI, exact McNemar test,
                 Holm-corrected p-value and a verdict
              3. calibration of confidence_score (ECE, Brier)
              4. seed consistency for temperatures above 0
WHERE IT FITS: Phase 7. Reads files written by run_benchmark.py; writes evaluation/reports/.
USE:          python -m evaluation.analyze_results <results.jsonl> [<more.jsonl> ...] \
                  --compare v3_fewshot@1.0.0 v6_critical_triggers@2.1.0 \
                  --report-name critical_fix_analysis
              A variant is written prompt_version@manifest_version.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from evaluation.significance import (
    PairedComparison,
    apply_holm_correction,
    bootstrap_mean_ci,
    calibration,
    compare_paired,
    minimum_detectable_difference,
    per_case_scores,
    seed_consistency,
)
from evaluation.summarize_results import load_quality_frame
from prompt_engine.settings import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
CONDITION_KEYS = ["model_name", "temperature", "constrained_decoding"]
# (metric, ticket subset, label): what every requested comparison is tested on.
COMPARISON_TARGETS = [
    ("all_labels_correct", None, "all labels, all tickets"),
    ("urgency_correct", None, "urgency, all tickets"),
    ("urgency_correct", "critical", "urgency, critical tickets (= critical recall)"),
]


# --- 1. Load one or more result files into one frame -------------------------------------------
def load_analysis_frame(results_paths: list[Path]) -> pd.DataFrame:
    frame = pd.concat(
        [load_quality_frame(results_path)[0] for results_path in results_paths],
        ignore_index=True,
    )
    dataset_hashes = frame["dataset_sha256"].unique()
    if len(dataset_hashes) > 1:
        raise ValueError(f"results come from different answer keys: {list(dataset_hashes)}")
    frame["variant_id"] = frame["prompt_version"] + "@" + frame["manifest_version"]
    # The same run can appear in two experiment files; count it once.
    return frame.drop_duplicates("run_key", keep="last").reset_index(drop=True)


def condition_label(model_name: str, temperature: float, constrained: bool) -> str:
    return f"{model_name} T={temperature}" + ("" if constrained else " unconstrained")


def format_with_ci(case_scores: pd.Series) -> str:
    low, high = bootstrap_mean_ci(case_scores.to_numpy())
    return f"{case_scores.mean():.2f} [{low:.2f}, {high:.2f}]"


# --- 2. Leaderboard ------------------------------------------------------------------------------
def leaderboard_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant_id, *condition), group in frame.groupby(["variant_id", *CONDITION_KEYS]):
        critical_group = group[group["expected_urgency"] == "critical"]
        not_critical = group[group["expected_urgency"] != "critical"]
        must_escalate = group[group["expected_escalation"]]
        critical_scores = per_case_scores(critical_group, "urgency_correct")
        rows.append({
            "variant": variant_id,
            "condition": condition_label(*condition),
            "tickets": group["case_id"].nunique(),
            "all labels [95% CI]": format_with_ci(per_case_scores(group, "all_labels_correct")),
            "urgency [95% CI]": format_with_ci(per_case_scores(group, "urgency_correct")),
            "critical caught": f"{critical_scores.sum():.1f}/{len(critical_scores)}",
            "false critical": f"{(not_critical['predicted_urgency'] == 'critical').mean():.2f}",
            "under-triage": f"{group['under_triaged'].mean():.2f}",
            "escalation recall": f"{must_escalate['escalation_correct'].mean():.2f}",
            "first-pass valid": f"{group['first_pass_valid'].mean():.2f}",
        })
    return pd.DataFrame(rows).sort_values(["condition", "variant"])


# --- 3. Paired comparisons (Holm-corrected together) -------------------------------------------
def only_subset(frame: pd.DataFrame, subset: str | None) -> pd.DataFrame:
    return frame if subset is None else frame[frame["expected_urgency"] == subset]


def run_comparisons(
    frame: pd.DataFrame, variant_pairs: list[tuple[str, str]]
) -> list[PairedComparison]:
    comparisons = []
    for baseline_id, candidate_id in variant_pairs:
        for variant_id in (baseline_id, candidate_id):
            if variant_id not in set(frame["variant_id"]):
                raise ValueError(f"{variant_id} not found; have {sorted(set(frame['variant_id']))}")
        for condition, condition_frame in frame.groupby(CONDITION_KEYS):
            baseline_frame = condition_frame[condition_frame["variant_id"] == baseline_id]
            candidate_frame = condition_frame[condition_frame["variant_id"] == candidate_id]
            if baseline_frame.empty or candidate_frame.empty:
                continue
            for metric, subset, target_label in COMPARISON_TARGETS:
                comparison = compare_paired(
                    only_subset(baseline_frame, subset), only_subset(candidate_frame, subset),
                    metric, (condition_label(*condition), baseline_id, candidate_id),
                )
                comparison.metric = target_label
                comparisons.append(comparison)
    apply_holm_correction(comparisons)
    return comparisons


def format_detectable(comparison: PairedComparison) -> str:
    detectable = minimum_detectable_difference(
        comparison.case_count, comparison.only_baseline_right + comparison.only_candidate_right
    )
    return "n/a" if detectable is None else f"±{min(detectable, 1.0):.2f}"


def comparisons_table(comparisons: list[PairedComparison]) -> pd.DataFrame:
    return pd.DataFrame([{
        "condition": comparison.condition,
        "baseline → candidate": f"{comparison.baseline} → {comparison.candidate}",
        "measured on": comparison.metric,
        "tickets": comparison.case_count,
        "baseline": f"{comparison.baseline_mean:.2f}",
        "candidate": f"{comparison.candidate_mean:.2f}",
        "difference [95% CI]": (
            f"{comparison.difference:+.2f} "
            f"[{comparison.difference_ci[0]:+.2f}, {comparison.difference_ci[1]:+.2f}]"
        ),
        "broke / fixed": f"{comparison.only_baseline_right} / {comparison.only_candidate_right}",
        "McNemar p": f"{comparison.mcnemar_p:.3f}",
        "Holm p": f"{comparison.holm_p:.3f}" if comparison.holm_p is not None else "",
        "detectable (80% power)": format_detectable(comparison),
        "verdict": comparison.verdict,
    } for comparison in comparisons])


# --- 4. Calibration and consistency --------------------------------------------------------------
def calibration_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant_id, *condition), group in frame.groupby(["variant_id", *CONDITION_KEYS]):
        answered = group.dropna(subset=["confidence_score"])
        if answered.empty:
            continue
        result = calibration(
            answered["confidence_score"].to_numpy(),
            (answered["category_correct"] & answered["urgency_correct"]).to_numpy(),
        )
        rows.append({
            "variant": variant_id, "condition": condition_label(*condition),
            "answers": result.answer_count,
            "mean confidence": f"{result.mean_confidence:.2f}",
            "actual accuracy": f"{result.accuracy:.2f}",
            "overconfidence": f"{result.mean_confidence - result.accuracy:+.2f}",
            "ECE": f"{result.expected_calibration_error:.2f}",
            "Brier": f"{result.brier_score:.3f}",
        })
    return pd.DataFrame(rows).sort_values(["condition", "variant"])


def consistency_table(frame: pd.DataFrame) -> pd.DataFrame:
    stochastic = frame[(frame["temperature"] > 0) & frame["schema_valid"]]
    if stochastic.empty:
        return pd.DataFrame()
    return pd.DataFrame([{
        "variant": variant_id, "condition": condition_label(*condition),
        "seeds per ticket": int(group.groupby("case_id").size().median()),
        "same answer across seeds": f"{seed_consistency(group):.2f}",
    } for (variant_id, *condition), group in stochastic.groupby(["variant_id", *CONDITION_KEYS])])


# --- 5. The report -----------------------------------------------------------------------------
def build_report(
    frame: pd.DataFrame, comparisons: list[PairedComparison], results_paths: list[Path]
) -> str:
    sections = [
        "# Benchmark analysis",
        "",
        f"Sources: {', '.join(f'`{path.name}`' for path in results_paths)} · "
        f"{len(frame)} scored runs · {frame['case_id'].nunique()} tickets · "
        f"answer key `{frame['dataset_sha256'].iloc[0]}` · split `{frame['split'].iloc[0]}`",
        "",
        "Intervals are 95% cluster-bootstrap CIs: tickets are resampled, so repeated runs of one "
        "ticket count as one ticket.",
        "",
        "## 1. Leaderboard",
        "",
        leaderboard_table(frame).to_markdown(index=False),
    ]
    if comparisons:
        sections += [
            "", "## 2. Paired comparisons", "",
            "Same tickets, two variants. *broke / fixed* = tickets only the baseline / only the "
            "candidate got right (the only tickets McNemar uses). Holm corrects for running "
            f"{len(comparisons)} tests at once; the verdict uses the Holm p-value at 0.05. "
            "*detectable* = the smallest true difference these tickets would catch 80% of the "
            "time: a smaller observed gap with no verdict means 'not measurable here', not 'none'.",
            "", comparisons_table(comparisons).to_markdown(index=False),
        ]
    sections += [
        "", "## 3. Calibration of confidence_score", "",
        "confidence_score claims P(category AND urgency correct). ECE 0 = perfectly calibrated; "
        "positive overconfidence = the model is surer than it is right.",
        "", calibration_table(frame).to_markdown(index=False),
    ]
    consistency = consistency_table(frame)
    if not consistency.empty:
        sections += ["", "## 4. Seed consistency (temperature > 0)", "",
                     consistency.to_markdown(index=False)]
    return "\n".join(sections) + "\n"


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("results_paths", type=Path, nargs="+")
    argument_parser.add_argument(
        "--compare", nargs=2, action="append", default=[], metavar=("BASELINE", "CANDIDATE"),
        help="variant ids as prompt_version@manifest_version; repeatable",
    )
    argument_parser.add_argument("--report-name", required=True)
    parsed_args = argument_parser.parse_args()

    frame = load_analysis_frame(parsed_args.results_paths)
    comparisons = run_comparisons(frame, [tuple(pair) for pair in parsed_args.compare])
    report_text = build_report(frame, comparisons, parsed_args.results_paths)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{parsed_args.report_name}.md"
    report_path.write_text(report_text, encoding="utf-8", newline="\n")
    print(report_text)
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
