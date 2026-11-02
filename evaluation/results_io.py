"""
FILE:         evaluation/results_io.py
WHAT IT DOES: Reads benchmark result files (JSONL, one row per run) and resolves repeats: when a
              run was retried after an infrastructure error, only its latest successful row counts.
WHERE IT FITS: Phase 6. Shared by the runner (to resume) and by analysis (to summarise).
"""

import json
import sys
from pathlib import Path
from typing import Any


# A run killed mid-write (Ctrl+C, power loss) can leave a half-written LAST line. That run is
# simply not done yet, so the line is skipped and the run is redone on resume. A broken line
# anywhere else means the file is damaged, which is an error.
def load_result_records(results_path: Path) -> list[dict[str, Any]]:
    if not results_path.exists():
        return []
    lines = [line for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = []
    for line_number, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as decode_error:
            if line_number < len(lines):
                raise ValueError(f"{results_path.name}:{line_number} is not valid JSON") from (
                    decode_error
                )
            print(f"WARNING: skipping a half-written last line in {results_path.name}",
                  file=sys.stderr)
    return records


# Every complete row ends with "\n", so text after the last "\n" is a half-written row. The runner
# cuts it off before appending; otherwise the next row would be glued onto it.
def drop_half_written_last_line(results_path: Path) -> None:
    if not results_path.exists():
        return
    content = results_path.read_bytes()
    if content and not content.endswith(b"\n"):
        results_path.write_bytes(content[: content.rfind(b"\n") + 1])


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
