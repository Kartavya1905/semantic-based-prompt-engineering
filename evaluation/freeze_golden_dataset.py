"""
FILE:         evaluation/freeze_golden_dataset.py
WHAT IT DOES: "Freezes" a golden dataset: writes <name>.manifest.json next to it with the file's
              SHA-256, version, annotation status and coverage counts.
WHERE IT FITS: Phase 5. A test compares the live file to this hash, so any edit to the dataset
              fails CI until it is re-frozen with a new dataset_version. Results from different
              hashes must never be compared.
USE:          python -m evaluation.freeze_golden_dataset <dataset.jsonl>
              python -m evaluation.freeze_golden_dataset <dataset.jsonl> --check
              python -m evaluation.freeze_golden_dataset <dataset.jsonl> \
                  --annotation-status adjudicated
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from evaluation.golden_case_model import compute_dataset_sha256, load_golden_cases

ANNOTATION_STATUSES = ("draft_single_annotator", "double_annotated", "adjudicated")


def manifest_path_for(dataset_path: Path) -> Path:
    return dataset_path.with_suffix(".manifest.json")


# --- 1. Everything a reader needs to know about the frozen file ---
def build_manifest(dataset_path: Path, annotation_status: str) -> dict:
    golden_cases = load_golden_cases(dataset_path)
    return {
        "dataset_file": dataset_path.name,
        "dataset_version": golden_cases[0].dataset_version,
        "sha256": compute_dataset_sha256(dataset_path),
        "annotation_status": annotation_status,
        "annotator_ids": sorted({aid for case in golden_cases for aid in case.annotator_ids}),
        "case_count": len(golden_cases),
        "split_counts": dict(sorted(Counter(case.split for case in golden_cases).items())),
        "category_counts": dict(sorted(
            Counter(case.expected_output["category"] for case in golden_cases).items()
        )),
        "urgency_counts": dict(sorted(
            Counter(case.expected_output["urgency"] for case in golden_cases).items()
        )),
        "slice_counts": dict(sorted(
            Counter(tag for case in golden_cases for tag in case.slice_tags).items()
        )),
    }


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("dataset_path", type=Path)
    argument_parser.add_argument("--check", action="store_true", help="exit 1 if hash is stale")
    argument_parser.add_argument("--annotation-status", choices=ANNOTATION_STATUSES)
    parsed_args = argument_parser.parse_args()
    manifest_path = manifest_path_for(parsed_args.dataset_path)

    # --- 2. --check: compare the live file with the frozen hash ---
    if parsed_args.check:
        stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        live_sha256 = compute_dataset_sha256(parsed_args.dataset_path)
        if live_sha256 != stored_manifest["sha256"]:
            print(f"[STALE] {parsed_args.dataset_path.name} changed since it was frozen. "
                  "Bump dataset_version, then re-run without --check.")
            return 1
        print(f"[OK] {parsed_args.dataset_path.name} matches its manifest")
        return 0

    # --- 3. Write the manifest (keep the previous status unless a new one is given) ---
    previous_status = (
        json.loads(manifest_path.read_text(encoding="utf-8"))["annotation_status"]
        if manifest_path.exists() else ANNOTATION_STATUSES[0]
    )
    manifest = build_manifest(
        parsed_args.dataset_path, parsed_args.annotation_status or previous_status
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"[FROZEN] {manifest_path.name}: v{manifest['dataset_version']} "
          f"{manifest['case_count']} cases, sha256={manifest['sha256'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
