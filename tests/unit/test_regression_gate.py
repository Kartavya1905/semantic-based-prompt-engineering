"""
FILE:         tests/unit/test_regression_gate.py
WHAT IT DOES: Checks the regression gate on hand-built results: unchanged results pass, small
              noise is tolerated, real regressions fail, safety tickets are protected on their
              own, and a changed answer key forces re-approval.
WHERE IT FITS: Phase 8.
"""

from pathlib import Path

import pandas as pd
import pytest

from evaluation.regression_gate import (
    GateConfig,
    build_baseline,
    load_gate_config,
    run_gate_checks,
    select_variant_rows,
)
from prompt_engine.settings import PROJECT_ROOT

GATE = GateConfig(
    gate_id="unit_gate", description="Gate used by unit tests.",
    experiment_config=Path("configs/experiments/ci_smoke.yaml"),
    prompt_version="v6_critical_triggers", model_name="test-model",
    min_schema_valid_rate=0.9, max_net_regressions=1,
    max_new_missed_escalations=0, max_new_missed_critical=0,
)

# Ten tickets: TT-00 is critical (and must escalate), TT-01 must escalate, the rest are routine.
EXPECTED = {f"TT-{i:02d}": ("critical" if i == 0 else "medium", i in (0, 1)) for i in range(10)}


# --- 1. Helpers: results where we choose exactly which tickets go wrong ---------------------------
def make_rows(wrong=(), missed_escalation=(), missed_critical=(), invalid=(),
              fingerprint="fp-approved", completed_at="2026-11-02T10:00:00+00:00",
              dataset_sha256="aaaaaaaaaaaa") -> pd.DataFrame:
    rows = []
    for case_id, (expected_urgency, expected_escalation) in EXPECTED.items():
        rows.append({
            "case_id": case_id, "prompt_version": "v6_critical_triggers",
            "manifest_version": "2.1.0", "prompt_fingerprint": fingerprint,
            "model_name": "test-model", "completed_at": completed_at,
            "dataset_sha256": dataset_sha256,
            "expected_urgency": expected_urgency, "expected_escalation": expected_escalation,
            "schema_valid": case_id not in invalid,
            "all_labels_correct": case_id not in (*wrong, *missed_escalation, *missed_critical,
                                                  *invalid),
            "escalation_correct": case_id not in (*missed_escalation, *invalid),
            "urgency_correct": case_id not in (*missed_critical, *invalid),
        })
    return pd.DataFrame(rows)


def check(candidate_rows, baseline_rows=None) -> dict[str, bool]:
    baseline = build_baseline(baseline_rows if baseline_rows is not None else make_rows(), GATE)
    checks = run_gate_checks(candidate_rows, baseline, GATE)
    return {gate_check.name: gate_check.passed for gate_check in checks}


# --- 2. Passing cases -----------------------------------------------------------------------
def test_identical_results_pass():
    assert all(check(make_rows()).values())


def test_one_broken_ticket_is_tolerated_as_noise():
    assert all(check(make_rows(wrong=("TT-05",))).values())


def test_breaking_one_and_fixing_one_nets_out():
    baseline_rows = make_rows(wrong=("TT-07",))
    candidate_rows = make_rows(wrong=("TT-05", "TT-06"))  # broke 2, fixed 1 → net +1
    assert all(check(candidate_rows, baseline_rows).values())


def test_an_edited_prompt_is_judged_against_the_approved_one():
    edited_prompt_rows = make_rows(fingerprint="fp-edited")
    assert all(check(edited_prompt_rows).values())


# --- 3. Failing cases -----------------------------------------------------------------------
def test_two_net_regressions_fail():
    assert check(make_rows(wrong=("TT-05", "TT-06")))["net regressions (all labels)"] is False


def test_a_newly_missed_escalation_fails_even_if_other_tickets_improve():
    baseline_rows = make_rows(wrong=("TT-05", "TT-06"))
    candidate_rows = make_rows(missed_escalation=("TT-01",))  # fixed 2, broke 1 → net -1
    results = check(candidate_rows, baseline_rows)
    assert results["net regressions (all labels)"] is True
    assert results["no newly missed escalations"] is False


def test_a_newly_missed_critical_ticket_fails():
    assert check(make_rows(missed_critical=("TT-00",)))["no newly missed critical tickets"] is False


def test_broken_json_fails_the_schema_floor():
    assert check(make_rows(invalid=("TT-05", "TT-06")))["schema validity"] is False  # 0.8 < 0.9


def test_a_changed_answer_key_forces_reapproval():
    results = check(make_rows(dataset_sha256="bbbbbbbbbbbb"))
    assert results["same answer key"] is False


def test_missing_tickets_fail():
    candidate_rows = make_rows()
    results = check(candidate_rows[candidate_rows["case_id"] != "TT-09"])
    assert results["all baseline tickets answered"] is False


# --- 4. Selecting the rows under test -----------------------------------------------------------
def test_only_the_current_prompt_is_under_test_even_after_a_revert():
    # A bad edit ran AFTER the approved prompt; then the edit was reverted on disk.
    approved_rows = make_rows(fingerprint="fp-approved", completed_at="2026-11-01T10:00:00+00:00")
    reverted_bad_rows = make_rows(wrong=("TT-05", "TT-06"), fingerprint="fp-bad-edit",
                                  completed_at="2026-11-02T10:00:00+00:00")
    selected = select_variant_rows(pd.concat([approved_rows, reverted_bad_rows]), GATE,
                                   prompt_fingerprint="fp-approved")
    assert set(selected["prompt_fingerprint"]) == {"fp-approved"}


def test_missing_results_for_the_current_prompt_say_what_to_run():
    with pytest.raises(ValueError, match="no results for v6_critical_triggers .* run `python -m"):
        select_variant_rows(make_rows(), GATE, prompt_fingerprint="fp-never-benchmarked")


def test_results_from_an_older_answer_key_are_left_out():
    # The same prompt run against answer key v1 (36 tickets) and v2: only v2 rows are checked.
    old_key_rows = make_rows(dataset_sha256="old-key-v1xx")
    current_key_rows = make_rows(dataset_sha256="new-key-v2xx", completed_at="2026-11-03")
    selected = select_variant_rows(
        pd.concat([old_key_rows, current_key_rows]), GATE,
        prompt_fingerprint="fp-approved", dataset_sha256="new-key-v2xx",
    )
    assert set(selected["dataset_sha256"]) == {"new-key-v2xx"}
    assert len(selected) == len(current_key_rows)


def test_current_fingerprint_matches_the_composer():
    from evaluation.regression_gate import current_prompt_fingerprint
    from prompt_engine.composer import PromptComposer
    from prompt_engine.registry import PromptRegistry

    gate = load_gate_config(PROJECT_ROOT / "configs" / "gates" / "dev_qwen7b.yaml")
    registry = PromptRegistry()
    manifest = registry.load_manifest("ticket_triage", "v6_critical_triggers")
    some_ticket = {"customer_tier": "pro", "ticket_subject": "x", "ticket_body": "y"}
    expected = PromptComposer(registry).compose(manifest, some_ticket).prompt_fingerprint
    assert current_prompt_fingerprint(gate) == expected


@pytest.mark.parametrize("gate_file", sorted((PROJECT_ROOT / "configs" / "gates").glob("*.yaml")))
def test_committed_gate_configs_are_valid(gate_file):
    gate = load_gate_config(gate_file)
    assert (PROJECT_ROOT / gate.experiment_config).is_file()
    assert gate.baseline_path.is_file(), f"approve a baseline for {gate.gate_id}"
