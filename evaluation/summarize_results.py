"""
FILE:         evaluation/summarize_results.py
WHAT IT DOES: A first look at a results file: one row of averages per
              (prompt variant, model, temperature, decoding mode), plus an optional per-slice view.
WHERE IT FITS: Phase 6 quick check. Phase 7 adds confidence intervals and significance tests;
              until then, small differences in this table are NOT evidence.
USE:          python -m evaluation.summarize_results evaluation/results/smoke.jsonl
              python -m evaluation.summarize_results evaluation/results/smoke.jsonl --by-slice
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from evaluation.results_io import latest_records_per_run, load_result_records

# manifest_version keeps edited prompts apart: v5 1.0.0 and v5 1.0.1 are different prompts and
# appear as separate rows (a before/after view) instead of being averaged together.
VARIANT_KEYS = [
    "prompt_version", "manifest_version", "model_name", "temperature", "constrained_decoding",
]


# --- 1. Rows → DataFrame of quality runs (infrastructure errors excluded) ----------------------
def load_quality_frame(results_path: Path) -> tuple[pd.DataFrame, int]:
    records = latest_records_per_run(load_result_records(results_path))
    if not records:
        raise ValueError(f"no results in {results_path}")
    results_frame = pd.DataFrame(records)
    infrastructure_failed = results_frame["infrastructure_error"].notna()
    quality_frame = results_frame[~infrastructure_failed].copy()
    # None (invalid answers) → NaN, so averages are over valid answers only for these columns.
    for optional_column in ("under_triaged", "summary_similarity", "confidence_score"):
        quality_frame[optional_column] = pd.to_numeric(quality_frame[optional_column])
    return quality_frame, int(infrastructure_failed.sum())


# --- 1b. Guard: one manifest version must mean one prompt ---------------------------------------
def versions_with_several_fingerprints(quality_frame: pd.DataFrame) -> list[str]:
    """A prompt file was edited without bumping the manifest version: its rows mix two prompts."""
    fingerprint_counts = quality_frame.groupby(
        ["prompt_version", "manifest_version"]
    )["prompt_fingerprint"].nunique()
    return [
        f"{prompt_version} {manifest_version}"
        for (prompt_version, manifest_version), count in fingerprint_counts.items()
        if count > 1
    ]


# --- 2. One row per variant ----------------------------------------------------------------------
def summarize_by_variant(quality_frame: pd.DataFrame) -> pd.DataFrame:
    variant_groups = quality_frame.groupby(VARIANT_KEYS)
    summary = variant_groups.agg(
        runs=("case_id", "size"),
        schema_valid=("schema_valid", "mean"),
        first_pass_valid=("first_pass_valid", "mean"),
        category_acc=("category_correct", "mean"),
        urgency_acc=("urgency_correct", "mean"),
        escalation_acc=("escalation_correct", "mean"),
        all_labels_acc=("all_labels_correct", "mean"),
        under_triage_rate=("under_triaged", "mean"),
        entity_f1=("entity_f1", "mean"),
        summary_similarity=("summary_similarity", "mean"),
        mean_latency_s=("total_latency_ms", lambda latencies: latencies.mean() / 1000),
    )
    # Escalation recall: of the tickets that MUST reach a human, how many did? (safety metric)
    must_escalate = quality_frame[quality_frame["expected_escalation"]]
    summary["escalation_recall"] = must_escalate.groupby(VARIANT_KEYS)["escalation_correct"].mean()
    # Critical recall: of the tickets that ARE critical, how many were rated critical?
    truly_critical = quality_frame[quality_frame["expected_urgency"] == "critical"]
    summary["critical_recall"] = truly_critical.groupby(VARIANT_KEYS)["urgency_correct"].mean()
    # Over-call check: of tickets that are NOT critical, how many were wrongly rated critical?
    not_critical = quality_frame[quality_frame["expected_urgency"] != "critical"]
    summary["false_critical_rate"] = (
        not_critical.assign(said_critical=not_critical["predicted_urgency"] == "critical")
        .groupby(VARIANT_KEYS)["said_critical"].mean()
    )
    return summary.round(3)


# --- 3. Per-slice view: which kinds of ticket does each variant struggle with? -----------------
def summarize_by_slice(quality_frame: pd.DataFrame) -> pd.DataFrame:
    slice_rows = quality_frame.explode("slice_tags").dropna(subset=["slice_tags"])
    return (
        slice_rows.pivot_table(
            index="slice_tags", columns=["prompt_version", "manifest_version"],
            values="all_labels_correct",
            aggfunc="mean",
        )
        .round(2)
    )


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("results_path", type=Path)
    argument_parser.add_argument("--by-slice", action="store_true")
    parsed_args = argument_parser.parse_args()

    quality_frame, infrastructure_error_count = load_quality_frame(parsed_args.results_path)
    print(f"{len(quality_frame)} scored runs, {infrastructure_error_count} infrastructure errors "
          "(excluded)\n")
    for mixed_version in versions_with_several_fingerprints(quality_frame):
        print(f"WARNING: {mixed_version} mixes several prompt fingerprints: a prompt file changed "
              "without a manifest version bump, so its row averages different prompts.\n")
    print(summarize_by_variant(quality_frame).to_markdown())
    if parsed_args.by_slice:
        print("\nall_labels_correct by slice:\n")
        print(summarize_by_slice(quality_frame).to_markdown())
    print("\nNote: no confidence intervals yet (Phase 7). Treat small gaps as noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
