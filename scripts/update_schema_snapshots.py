"""
FILE:         scripts/update_schema_snapshots.py
WHAT IT DOES: Writes (or checks) tests/snapshots/<prompt_id>_schema.json for every registered
              output contract.
WHERE IT FITS: Run after an intentional schema change, then bump the affected manifests' MAJOR
              version. The snapshot test fails on any unintentional change.
USE:          python scripts/update_schema_snapshots.py           (rewrite snapshots)
              python scripts/update_schema_snapshots.py --check   (exit 1 if any are stale)
"""

import argparse
import sys

from prompt_engine.schemas import REGISTERED_CONTRACTS, render_schema_snapshot
from prompt_engine.settings import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "tests" / "snapshots"


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--check", action="store_true", help="only report stale files")
    check_only = argument_parser.parse_args().check
    stale_snapshots = 0

    for prompt_id, contract in REGISTERED_CONTRACTS.items():
        snapshot_path = SNAPSHOT_DIR / f"{prompt_id}_schema.json"
        current_text = render_schema_snapshot(contract)
        stored_text = snapshot_path.read_text(encoding="utf-8") if snapshot_path.exists() else None

        # --- 1. Unchanged: nothing to do ---
        if stored_text == current_text:
            print(f"[OK]      {snapshot_path.relative_to(PROJECT_ROOT)}")
            continue
        stale_snapshots += 1
        # --- 2. Changed: report, or rewrite the file ---
        if check_only:
            print(f"[STALE]   {snapshot_path.relative_to(PROJECT_ROOT)}")
        else:
            snapshot_path.write_text(current_text, encoding="utf-8", newline="\n")
            print(f"[WRITTEN] {snapshot_path.relative_to(PROJECT_ROOT)}")

    if check_only and stale_snapshots:
        print("Schema changed: run without --check, then bump the manifests' MAJOR version.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
