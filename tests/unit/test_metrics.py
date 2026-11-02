"""
FILE:         tests/unit/test_metrics.py
WHAT IT DOES: Checks per-case scoring: correct and wrong labels, under/over-triage direction,
              entity precision/recall, and how invalid answers are scored.
WHERE IT FITS: Phase 6.
"""

import pytest

from evaluation.golden_case_model import load_golden_cases
from evaluation.metrics import entity_set_scores, score_case
from prompt_engine.pipeline import AttemptRecord, PipelineOutcome
from prompt_engine.schemas import validate_as_model_output
from prompt_engine.schemas.ticket_triage import TicketTriageResult
from prompt_engine.settings import PROJECT_ROOT

DATASET_PATH = PROJECT_ROOT / "evaluation" / "golden_datasets" / "ticket_triage" / "v1.jsonl"


# --- 1. Helpers: build outcomes the way the pipeline would -------------------------------------
@pytest.fixture(scope="module")
def outage_case():
    return next(case for case in load_golden_cases(DATASET_PATH) if case.case_id == "TT-0012")


def correct_answer(golden_case) -> dict:
    return golden_case.expected_output | {
        "summary": golden_case.reference_summary, "confidence_score": 0.9,
    }


def make_outcome(answer: dict | None, attempts: int = 1, first_error: str = "json_invalid"):
    attempt_records = [
        AttemptRecord(
            number, "{...}", 100.0, 900, 50, "stop",
            None if (answer is not None and number == attempts) else [{"type": first_error}],
        )
        for number in range(1, attempts + 1)
    ]
    parsed = validate_as_model_output(TicketTriageResult, answer) if answer else None
    return PipelineOutcome(
        prompt_fingerprint="abc123", parsed_output=parsed, attempts=attempt_records
    )


# --- 2. Label scoring ----------------------------------------------------------------------------
def test_correct_answer_scores_perfectly(outage_case):
    row = score_case(outage_case, make_outcome(correct_answer(outage_case)))
    assert row["schema_valid"] and row["first_pass_valid"]
    assert row["category_correct"] and row["urgency_correct"] and row["escalation_correct"]
    assert row["all_labels_correct"]
    assert row["urgency_distance"] == 0 and row["under_triaged"] is False
    assert row["entity_f1"] == 1.0
    assert row["first_attempt_error_types"] == []


def test_high_instead_of_critical_is_under_triage(outage_case):
    answer = correct_answer(outage_case) | {"urgency": "high"}  # what qwen2.5:7b really answered
    row = score_case(outage_case, make_outcome(answer))
    assert not row["urgency_correct"] and not row["all_labels_correct"]
    assert row["category_correct"] and row["escalation_correct"]
    assert row["urgency_distance"] == -1 and row["under_triaged"] is True


def test_too_urgent_is_over_triage_not_under(outage_case):
    low_urgency_labels = outage_case.expected_output | {
        "urgency": "low", "requires_human_escalation": False,
    }
    low_urgency_case = outage_case.model_copy(update={"expected_output": low_urgency_labels})
    row = score_case(low_urgency_case, make_outcome(correct_answer(outage_case)))  # says critical
    assert row["urgency_distance"] == 3 and row["under_triaged"] is False


def test_repaired_answer_is_valid_but_not_first_pass(outage_case):
    row = score_case(outage_case, make_outcome(correct_answer(outage_case), attempts=2))
    assert row["schema_valid"] and not row["first_pass_valid"]
    assert row["attempts_used"] == 2
    assert row["first_attempt_error_types"] == ["json_invalid"]


def test_invalid_answer_scores_as_wrong_everywhere(outage_case):
    row = score_case(outage_case, make_outcome(None, attempts=3))
    assert not row["schema_valid"] and not row["all_labels_correct"]
    assert row["predicted_category"] is None and row["under_triaged"] is None
    assert row["entity_f1"] == 0.0
    assert row["expected_urgency"] == "critical"  # the key is still recorded


# --- 3. Entity scoring ---------------------------------------------------------------------------
def entity(entity_type, entity_value):
    return {"entity_type": entity_type, "entity_value": entity_value}


@pytest.mark.parametrize(("predicted", "expected", "scores"), [
    ([], [], (1.0, 1.0, 1.0)),
    ([entity("error_code", "e-5012")], [entity("error_code", "E-5012")], (1.0, 1.0, 1.0)),
    ([], [entity("error_code", "E-5012")], (0.0, 0.0, 0.0)),
    ([entity("error_code", "E-5012"), entity("order_id", "ORD-1")],
     [entity("error_code", "E-5012")], (0.5, 1.0, 2 / 3)),
    ([entity("order_id", "E-5012")], [entity("error_code", "E-5012")], (0.0, 0.0, 0.0)),
])
def test_entity_set_scores(predicted, expected, scores):
    result = entity_set_scores(predicted, expected)
    assert (result["entity_precision"], result["entity_recall"]) == pytest.approx(scores[:2])
    assert result["entity_f1"] == pytest.approx(scores[2])
