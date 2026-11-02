"""
FILE:         tests/unit/test_ticket_triage_schema.py
WHAT IT DOES: Proves the ticket_triage output contract accepts good answers and rejects every
              kind of bad answer a model can produce: broken JSON, wrong shape, out-of-vocabulary
              values, out-of-range numbers, and business-rule violations.
WHERE IT FITS: Phase 1. Inputs are raw JSON strings because that is exactly what the Phase 4
              pipeline receives from the model.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from prompt_engine.schemas import (
    REGISTERED_CONTRACTS,
    render_schema_snapshot,
    validate_as_model_output,
)
from prompt_engine.schemas.ticket_triage import (
    EntityType,
    TicketCategory,
    TicketTriageResult,
    UrgencyLevel,
)

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "snapshots"


# --- 1. A known-good answer; each test breaks exactly one thing in a copy of it ---------------
def build_valid_answer() -> dict:
    return {
        "summary": "Enterprise customer reports /v2/orders failing with E-5012 since 09:14 UTC.",
        "extracted_entities": [{"entity_type": "error_code", "entity_value": "E-5012"}],
        "category": "technical",
        "urgency": "critical",
        "requires_human_escalation": True,
        "confidence_score": 0.92,
    }


def parse_answer(answer: dict) -> TicketTriageResult:
    return TicketTriageResult.model_validate_json(json.dumps(answer))


def assert_rejected(answer: dict, expected_error_type: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_answer(answer)
    reported_types = {error["type"] for error in caught.value.errors()}
    assert expected_error_type in reported_types, reported_types


# --- 2. Accepts valid answers and parses them into typed values ---------------------------------
def test_valid_answer_parses_to_enums():
    parsed = parse_answer(build_valid_answer())
    assert parsed.category is TicketCategory.TECHNICAL
    assert parsed.urgency is UrgencyLevel.CRITICAL
    assert parsed.extracted_entities[0].entity_type is EntityType.ERROR_CODE


def test_empty_entity_list_is_allowed():
    answer = build_valid_answer() | {"extracted_entities": []}
    assert parse_answer(answer).extracted_entities == []


def test_whitespace_is_stripped_from_strings():
    answer = build_valid_answer()
    answer["extracted_entities"] = [{"entity_type": "error_code", "entity_value": "  E-5012 "}]
    assert parse_answer(answer).extracted_entities[0].entity_value == "E-5012"


# --- 3. Layer 1 failures: syntax and shape ------------------------------------------------------
def test_malformed_json_is_a_validation_error():
    # The pipeline catches ONE exception type for both broken JSON and wrong content.
    with pytest.raises(ValidationError) as caught:
        TicketTriageResult.model_validate_json('{"summary": "unterminated')
    assert caught.value.errors()[0]["type"] == "json_invalid"


def test_unknown_field_is_rejected():
    assert_rejected(build_valid_answer() | {"reasoning": "I think..."}, "extra_forbidden")


@pytest.mark.parametrize("required_field", list(build_valid_answer()))
def test_every_field_is_required(required_field):
    answer = build_valid_answer()
    del answer[required_field]
    assert_rejected(answer, "missing")


# --- 4. Layer 2 failures: vocabulary, types and ranges ------------------------------------------
@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [("category", "Technical"), ("category", "outage"), ("urgency", "urgent")],
)
def test_out_of_vocabulary_values_are_rejected(field_name, bad_value):
    assert_rejected(build_valid_answer() | {field_name: bad_value}, "enum")


@pytest.mark.parametrize("bad_score", [-0.1, 1.01, 92])
def test_confidence_must_be_a_probability(bad_score):
    error_type = "greater_than_equal" if bad_score < 0 else "less_than_equal"
    assert_rejected(build_valid_answer() | {"confidence_score": bad_score}, error_type)


def test_summary_length_bounds():
    assert_rejected(build_valid_answer() | {"summary": "Broken."}, "string_too_short")
    assert_rejected(build_valid_answer() | {"summary": "x" * 281}, "string_too_long")


def test_entity_list_is_capped():
    answer = build_valid_answer()
    answer["extracted_entities"] = [
        {"entity_type": "order_id", "entity_value": f"ORD-{number}"} for number in range(11)
    ]
    assert_rejected(answer, "too_long")


@pytest.mark.parametrize("stringly_boolean", ["yes", "true", "1"])
def test_escalation_must_be_a_real_json_boolean(stringly_boolean):
    # Strict mode: lax Pydantic would coerce all three strings to True.
    answer = build_valid_answer() | {"requires_human_escalation": stringly_boolean}
    assert_rejected(answer, "bool_type")


def test_confidence_must_be_a_real_json_number():
    assert_rejected(build_valid_answer() | {"confidence_score": "0.9"}, "float_type")


# --- 5. Layer 3 failures: business rules (cross-field semantics) --------------------------------
def test_critical_without_escalation_is_rejected():
    answer = build_valid_answer() | {"requires_human_escalation": False}
    with pytest.raises(ValidationError, match="requires requires_human_escalation=true"):
        parse_answer(answer)


def test_non_critical_may_skip_escalation():
    answer = build_valid_answer() | {"urgency": "high", "requires_human_escalation": False}
    assert parse_answer(answer).requires_human_escalation is False


def test_duplicate_entities_are_rejected_case_insensitively():
    answer = build_valid_answer()
    answer["extracted_entities"] = [
        {"entity_type": "error_code", "entity_value": "E-5012"},
        {"entity_type": "error_code", "entity_value": "e-5012"},
    ]
    with pytest.raises(ValidationError, match="duplicates"):
        parse_answer(answer)


# --- 6. Dicts from YAML/JSONL (few-shots, golden answers) use the model-output rules -----------
def test_plain_dict_fails_strict_python_mode_but_passes_helper():
    answer = build_valid_answer()
    with pytest.raises(ValidationError):
        TicketTriageResult.model_validate(answer)  # strict: "technical" is not a TicketCategory
    assert validate_as_model_output(TicketTriageResult, answer).category is TicketCategory.TECHNICAL


def test_helper_still_enforces_strict_types():
    answer = build_valid_answer() | {"requires_human_escalation": "yes"}
    with pytest.raises(ValidationError):
        validate_as_model_output(TicketTriageResult, answer)


# --- 7. Contract stability: the JSON Schema the prompt will embed -------------------------------
@pytest.mark.parametrize("prompt_id", list(REGISTERED_CONTRACTS))
def test_schema_matches_committed_snapshot(prompt_id):
    """Fails on ANY schema change, including field reordering.
    Intentional change → python scripts/update_schema_snapshots.py + MAJOR manifest bump."""
    snapshot_path = SNAPSHOT_DIR / f"{prompt_id}_schema.json"
    stored_text = snapshot_path.read_text(encoding="utf-8")
    assert render_schema_snapshot(REGISTERED_CONTRACTS[prompt_id]) == stored_text


def test_schema_field_order_puts_evidence_before_decisions():
    property_order = list(TicketTriageResult.model_json_schema()["properties"])
    assert property_order.index("summary") < property_order.index("category")
    assert property_order.index("extracted_entities") < property_order.index("urgency")


def test_schema_forbids_extra_keys_at_every_level():
    json_schema = TicketTriageResult.model_json_schema()
    assert json_schema["additionalProperties"] is False
    assert json_schema["$defs"]["ExtractedEntity"]["additionalProperties"] is False
