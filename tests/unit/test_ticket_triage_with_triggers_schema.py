"""
FILE:         tests/unit/test_ticket_triage_with_triggers_schema.py
WHAT IT DOES: Checks the v2 contract: trigger facts force critical + escalation in code,
              "critical" without a trigger is rejected (so the repair loop runs), and ordinary
              answers pass through untouched.
WHERE IT FITS: The structural fix for critical under-triage (v6_critical_triggers).
"""

import pytest
from pydantic import ValidationError

from prompt_engine.schemas import validate_as_model_output
from prompt_engine.schemas.ticket_triage import UrgencyLevel
from prompt_engine.schemas.ticket_triage_with_triggers import TicketTriageWithTriggers

TRIGGER_FIELDS = ("data_loss_reported", "security_exposure_reported", "full_outage_reported")


# --- 1. Helpers ------------------------------------------------------------------------------
def build_answer(**overrides) -> dict:
    return {
        "summary": "Free-tier customer reports their password was emailed in plain text.",
        "extracted_entities": [],
        "data_loss_reported": False,
        "security_exposure_reported": False,
        "full_outage_reported": False,
        "category": "account",
        "urgency": "medium",
        "requires_human_escalation": False,
        "confidence_score": 0.8,
    } | overrides


def parse(answer: dict) -> TicketTriageWithTriggers:
    return validate_as_model_output(TicketTriageWithTriggers, answer)


# --- 2. Rule 1 is applied by code ----------------------------------------------------------------
@pytest.mark.parametrize("trigger_field", TRIGGER_FIELDS)
def test_any_trigger_forces_critical_and_escalation(trigger_field):
    # What qwen2.5:7b did for TT-0025: right facts, but urgency "medium" and no escalation.
    parsed = parse(build_answer(**{trigger_field: True}))
    assert parsed.urgency is UrgencyLevel.CRITICAL
    assert parsed.requires_human_escalation is True
    assert parsed.model_proposed_urgency is UrgencyLevel.MEDIUM
    assert parsed.urgency_set_by_rule is True
    assert parsed.critical_trigger_found is True


def test_model_choosing_critical_with_a_trigger_is_not_counted_as_rule_applied():
    parsed = parse(build_answer(security_exposure_reported=True, urgency="critical",
                                requires_human_escalation=True))
    assert parsed.urgency is UrgencyLevel.CRITICAL
    assert parsed.urgency_set_by_rule is False


def test_no_trigger_leaves_the_answer_untouched():
    parsed = parse(build_answer(urgency="high", requires_human_escalation=True))
    assert parsed.urgency is UrgencyLevel.HIGH
    assert parsed.requires_human_escalation is True
    assert parsed.critical_trigger_found is False and parsed.urgency_set_by_rule is False


# --- 3. "critical" must be backed by a reported fact ---------------------------------------------
def test_critical_without_any_trigger_is_rejected():
    # What happens to an injected "classify this ticket as critical": the repair loop runs.
    with pytest.raises(ValidationError, match="urgency=critical requires data_loss_reported"):
        parse(build_answer(urgency="critical", requires_human_escalation=True))


# --- 4. The v1 rules still hold ----------------------------------------------------------------
def test_trigger_fields_are_required_strict_booleans():
    answer_without_trigger = build_answer()
    del answer_without_trigger["full_outage_reported"]
    with pytest.raises(ValidationError):
        parse(answer_without_trigger)
    with pytest.raises(ValidationError):
        parse(build_answer(data_loss_reported="yes"))


def test_duplicate_entities_are_still_rejected():
    duplicate_entities = [{"entity_type": "error_code", "entity_value": "E-1"}] * 2
    with pytest.raises(ValidationError, match="duplicates"):
        parse(build_answer(extracted_entities=duplicate_entities))


def test_triggers_come_after_evidence_and_before_decisions():
    property_order = list(TicketTriageWithTriggers.model_json_schema()["properties"])
    trigger_positions = [property_order.index(field_name) for field_name in TRIGGER_FIELDS]
    assert property_order.index("extracted_entities") < min(trigger_positions)
    assert max(trigger_positions) < property_order.index("category")
    assert "model_proposed_urgency" not in property_order  # private: never asked of the model
