"""
FILE:         evaluation/regression_gate.py
WHAT IT DOES: The guard at the door. A prompt change may only merge if, ticket by ticket, it does
              not break what the APPROVED version got right.
              approve → store the current results of the production variant as the baseline
                        (evaluation/baselines/<gate_id>.json, committed and reviewed like code)
              check   → compare fresh results against that baseline; exit 1 if any gate fails
WHERE IT FITS: Phase 8. CI runs the gate's small experiment, then `check`. Locally the same
              commands run against a bigger experiment with a bigger model.
WHY PER TICKET: on 11-36 tickets an average can hide a serious regression (one newly missed
              escalation cancelled out by one fixed typo). Counting broken vs fixed tickets, and
              protecting escalations and critical tickets separately, cannot be fooled that way.
USE:          python -m evaluation.regression_gate approve configs/gates/ci_smoke.yaml
              python -m evaluation.regression_gate check configs/gates/ci_smoke.yaml
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from evaluation.experiment_config import load_experiment_config
from evaluation.golden_case_model import load_golden_cases
from evaluation.summarize_results import load_quality_frame
from prompt_engine.composer import PromptComposer
from prompt_engine.registry import PromptRegistry
from prompt_engine.settings import PROJECT_ROOT, get_settings

BASELINES_DIR = PROJECT_ROOT / "evaluation" / "baselines"


# --- 1. Gate configuration (configs/gates/*.yaml) ----------------------------------------------
class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str
    experiment_config: Path            # the experiment whose results are checked
    prompt_version: str                # the production variant (any manifest version)
    model_name: str
    min_schema_valid_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    max_net_regressions: int = Field(default=1, ge=0)          # tickets broken minus fixed
    max_new_missed_escalations: int = Field(default=0, ge=0)   # safety: must-escalate tickets
    max_new_missed_critical: int = Field(default=0, ge=0)      # safety: critical tickets

    @property
    def baseline_path(self) -> Path:
        return BASELINES_DIR / f"{self.gate_id}.json"

    def default_results_path(self) -> Path:
        experiment = load_experiment_config(PROJECT_ROOT / self.experiment_config)
        return get_settings().results_dir / f"{experiment.experiment_id}.jsonl"


def load_gate_config(gate_path: Path) -> GateConfig:
    return GateConfig.model_validate(yaml.safe_load(gate_path.read_text(encoding="utf-8")))


# --- 2. Pick the rows under test: the gate's variant + model + the prompt AS IT IS ON DISK -------
# A results file may hold runs of several edits of the prompt (including a reverted bad edit).
# Only rows whose fingerprint matches the current prompt files say anything about this change.
def current_prompt_fingerprint(gate: GateConfig) -> str:
    experiment = load_experiment_config(PROJECT_ROOT / gate.experiment_config)
    registry = PromptRegistry()
    manifest = registry.load_manifest(experiment.prompt_id, gate.prompt_version)
    any_case = load_golden_cases(experiment.resolved_dataset_path)[0]
    return PromptComposer(registry).compose(manifest, any_case.input_variables).prompt_fingerprint


def select_variant_rows(
    quality_frame: pd.DataFrame, gate: GateConfig, prompt_fingerprint: str
) -> pd.DataFrame:
    variant_rows = quality_frame[
        (quality_frame["prompt_version"] == gate.prompt_version)
        & (quality_frame["model_name"] == gate.model_name)
        & (quality_frame["prompt_fingerprint"] == prompt_fingerprint)
    ]
    if variant_rows.empty:
        raise ValueError(
            f"no results for {gate.prompt_version} ({prompt_fingerprint}) on {gate.model_name}: "
            f"run `python -m evaluation.run_benchmark {gate.experiment_config.as_posix()}` first"
        )
    return variant_rows


def per_case_outcomes(variant_rows: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """One record per ticket. With several seeds, a ticket counts as right if most runs are."""
    outcomes = {}
    for case_id, case_rows in variant_rows.groupby("case_id"):
        outcomes[str(case_id)] = {
            "all_labels_correct": bool(case_rows["all_labels_correct"].mean() >= 0.5),
            "urgency_correct": bool(case_rows["urgency_correct"].mean() >= 0.5),
            "escalation_correct": bool(case_rows["escalation_correct"].mean() >= 0.5),
            "expected_urgency": case_rows["expected_urgency"].iloc[0],
            "expected_escalation": bool(case_rows["expected_escalation"].iloc[0]),
        }
    return outcomes


# --- 3. approve: freeze today's results as the bar future changes must clear ------------------
def build_baseline(variant_rows: pd.DataFrame, gate: GateConfig) -> dict[str, Any]:
    first_row = variant_rows.iloc[0]
    return {
        "gate_id": gate.gate_id,
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "approved_variant": f"{first_row['prompt_version']}@{first_row['manifest_version']}",
        "prompt_fingerprint": first_row["prompt_fingerprint"],
        "model_name": gate.model_name,
        "dataset_sha256": first_row["dataset_sha256"],
        "metrics": {
            "tickets": int(variant_rows["case_id"].nunique()),
            "schema_valid_rate": round(float(variant_rows["schema_valid"].mean()), 3),
            "all_labels_accuracy": round(float(variant_rows["all_labels_correct"].mean()), 3),
            "urgency_accuracy": round(float(variant_rows["urgency_correct"].mean()), 3),
        },
        "cases": per_case_outcomes(variant_rows),
    }


# --- 4. check: every gate is a named pass/fail with a human-readable reason ------------------
@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


def run_gate_checks(
    variant_rows: pd.DataFrame, baseline: dict[str, Any], gate: GateConfig
) -> list[GateCheck]:
    candidate_cases = per_case_outcomes(variant_rows)
    baseline_cases: dict[str, dict[str, Any]] = baseline["cases"]
    checks: list[GateCheck] = []

    # 4a. Same answer key and same tickets, or the comparison is meaningless.
    candidate_sha = variant_rows["dataset_sha256"].iloc[0]
    checks.append(GateCheck(
        "same answer key", candidate_sha == baseline["dataset_sha256"],
        f"baseline {baseline['dataset_sha256']}, candidate {candidate_sha}"
        + ("" if candidate_sha == baseline["dataset_sha256"] else ": re-approve the baseline"),
    ))
    missing_cases = sorted(set(baseline_cases) - set(candidate_cases))
    checks.append(GateCheck(
        "all baseline tickets answered", not missing_cases,
        "all present" if not missing_cases else f"missing {missing_cases}",
    ))
    shared_cases = sorted(set(baseline_cases) & set(candidate_cases))

    # 4b. Structure: answers must still parse.
    schema_valid_rate = float(variant_rows["schema_valid"].mean())
    checks.append(GateCheck(
        "schema validity", schema_valid_rate >= gate.min_schema_valid_rate,
        f"{schema_valid_rate:.2f} (floor {gate.min_schema_valid_rate:.2f})",
    ))

    # 4c. Quality: tickets broken vs fixed, compared ticket by ticket.
    def changed(field_name: str, cases: list[str]) -> tuple[list[str], list[str]]:
        broke = [c for c in cases
                 if baseline_cases[c][field_name] and not candidate_cases[c][field_name]]
        fixed = [c for c in cases
                 if not baseline_cases[c][field_name] and candidate_cases[c][field_name]]
        return broke, fixed

    broke, fixed = changed("all_labels_correct", shared_cases)
    net_regressions = len(broke) - len(fixed)
    checks.append(GateCheck(
        "net regressions (all labels)", net_regressions <= gate.max_net_regressions,
        f"broke {len(broke)} {broke}, fixed {len(fixed)} {fixed}; net {net_regressions:+d} "
        f"(max {gate.max_net_regressions:+d})",
    ))

    # 4d. Safety: newly missed escalations and critical tickets are counted on their own,
    # so fixing easy tickets can never pay for missing a dangerous one.
    must_escalate = [c for c in shared_cases if baseline_cases[c]["expected_escalation"]]
    missed_escalations, _ = changed("escalation_correct", must_escalate)
    checks.append(GateCheck(
        "no newly missed escalations", len(missed_escalations) <= gate.max_new_missed_escalations,
        f"{len(missed_escalations)} {missed_escalations} (max {gate.max_new_missed_escalations})",
    ))
    critical_cases = [
        c for c in shared_cases if baseline_cases[c]["expected_urgency"] == "critical"
    ]
    missed_critical, _ = changed("urgency_correct", critical_cases)
    checks.append(GateCheck(
        "no newly missed critical tickets", len(missed_critical) <= gate.max_new_missed_critical,
        f"{len(missed_critical)} {missed_critical} (max {gate.max_new_missed_critical})",
    ))
    return checks


def format_checks_markdown(gate: GateConfig, baseline: dict[str, Any], candidate_variant: str,
                           checks: list[GateCheck]) -> str:
    verdict = "PASSED" if all(check.passed for check in checks) else "FAILED"
    lines = [
        f"## Prompt regression gate `{gate.gate_id}`: {verdict}",
        "",
        f"Baseline `{baseline['approved_variant']}` (approved {baseline['approved_at']}) vs "
        f"candidate `{candidate_variant}` on `{gate.model_name}`",
        "",
        "| check | result | detail |",
        "|---|---|---|",
    ]
    lines += [f"| {check.name} | {'✅ pass' if check.passed else '❌ FAIL'} | {check.detail} |"
              for check in checks]
    return "\n".join(lines) + "\n"


# --- 5. CLI --------------------------------------------------------------------------------------
def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("command", choices=["approve", "check"])
    argument_parser.add_argument("gate_config", type=Path)
    argument_parser.add_argument("--results", type=Path, help="override the results file")
    parsed_args = argument_parser.parse_args()

    gate = load_gate_config(parsed_args.gate_config)
    results_path = parsed_args.results or gate.default_results_path()
    variant_rows = select_variant_rows(
        load_quality_frame(results_path)[0], gate, current_prompt_fingerprint(gate)
    )

    if parsed_args.command == "approve":
        baseline = build_baseline(variant_rows, gate)
        BASELINES_DIR.mkdir(parents=True, exist_ok=True)
        gate.baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8",
                                      newline="\n")
        print(f"Approved {baseline['approved_variant']} on {gate.model_name} as baseline "
              f"{gate.baseline_path.name}: {baseline['metrics']}")
        return 0

    if not gate.baseline_path.exists():
        print(f"No baseline at {gate.baseline_path}. Run `approve` first.")
        return 2
    baseline = json.loads(gate.baseline_path.read_text(encoding="utf-8"))
    checks = run_gate_checks(variant_rows, baseline, gate)
    first_row = variant_rows.iloc[0]
    report = format_checks_markdown(
        gate, baseline, f"{first_row['prompt_version']}@{first_row['manifest_version']} "
        f"({first_row['prompt_fingerprint']})", checks,
    )
    print(report)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):  # shows on the CI run page
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(report)
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
