"""
FILE:         evaluation/results_io.py
WHAT IT DOES: Reads benchmark result files (JSONL, one row per run) and resolves repeats: when a
              run was retried after an infrastructure error, only its latest successful row counts.
WHERE IT FITS: Phase 6. Shared by the runner (to resume) and by analysis (to summarise).
"""

import json
from pathlib import Path
from typing import Any


def load_result_records(results_path: Path) -> list[dict[str, Any]]:
    if not results_path.exists():
        return []
    with results_path.open(encoding="utf-8") as results_file:
        return [json.loads(line) for line in results_file if line.strip()]


def is_successful(record: dict[str, Any]) -> bool:
    return record.get("infrastructure_error") is None


# --- 1. Resume: a run is "done" only if it has a row without an infrastructure error ----------
def completed_run_keys(results_path: Path) -> set[str]:
    return {
        record["run_key"] for record in load_result_records(results_path) if is_successful(record)
    }


# --- 2. One row per run_key: the last successful row, else the last error row -----------------
def latest_records_per_run(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen_records: dict[str, dict[str, Any]] = {}
    for record in records:
        previous_record = chosen_records.get(record["run_key"])
        if previous_record is None or is_successful(record) or not is_successful(previous_record):
            chosen_records[record["run_key"]] = record
    return list(chosen_records.values())
