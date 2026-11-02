"""
FILE:         tests/unit/test_pipeline.py
WHAT IT DOES: Checks the validate-and-repair loop with a scripted fake model: first-pass success,
              repairs after broken JSON or broken business rules, giving up, and error handling.
WHERE IT FITS: Phase 4. Offline and exact: every model reply is chosen by the test.
"""

import json

import pytest

from prompt_engine.clients.base import LLMClient, LLMTransportError
from prompt_engine.composer import ComposedPrompt, PromptComposer
from prompt_engine.pipeline import REPAIR_INSTRUCTION, StructuredPromptPipeline
from prompt_engine.registry import PromptRegistry
from prompt_engine.schemas.ticket_triage import TicketTriageResult, UrgencyLevel
from tests.fakes import ScriptedLLMClient

SAMPLE_TICKET = {
    "customer_tier": "enterprise",
    "ticket_subject": "API down",
    "ticket_body": "Every call to /v2/orders fails with E-5012.",
}
VALID_ANSWER = {
    "summary": "Enterprise customer reports every /v2/orders call failing with E-5012.",
    "extracted_entities": [{"entity_type": "error_code", "entity_value": "E-5012"}],
    "category": "technical",
    "urgency": "critical",
    "requires_human_escalation": True,
    "confidence_score": 0.9,
}


# --- 1. Fixtures --------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def composed_prompt() -> ComposedPrompt:
    registry = PromptRegistry()
    manifest = registry.load_manifest("ticket_triage", "v1_baseline")
    return PromptComposer(registry).compose(manifest, SAMPLE_TICKET)


async def run_with_replies(composed_prompt, replies, **pipeline_options):
    fake_client = ScriptedLLMClient(list(replies))
    outcome = await StructuredPromptPipeline(fake_client, **pipeline_options).run(composed_prompt)
    return outcome, fake_client


def test_fake_satisfies_the_client_protocol():
    fake_client: LLMClient = ScriptedLLMClient([])  # mypy checks this assignment
    assert fake_client.model_name == "scripted-fake"


# --- 2. Success on the first attempt ------------------------------------------------------------
async def test_valid_first_reply_needs_no_repair(composed_prompt):
    outcome, fake_client = await run_with_replies(composed_prompt, [VALID_ANSWER])
    assert outcome.is_valid and outcome.first_pass_valid
    assert outcome.attempts_used == 1
    assert isinstance(outcome.parsed_output, TicketTriageResult)
    assert outcome.parsed_output.urgency is UrgencyLevel.CRITICAL
    assert outcome.prompt_fingerprint == composed_prompt.prompt_fingerprint
    assert len(fake_client.recorded_calls) == 1


async def test_first_call_sends_exactly_the_composed_prompt(composed_prompt):
    _, fake_client = await run_with_replies(composed_prompt, [VALID_ANSWER])
    first_call = fake_client.recorded_calls[0]
    assert first_call.messages == composed_prompt.as_messages()
    assert first_call.generation_params == composed_prompt.generation_params
    assert first_call.response_json_schema == TicketTriageResult.model_json_schema()


async def test_constrained_decoding_can_be_switched_off(composed_prompt):
    _, fake_client = await run_with_replies(
        composed_prompt, [VALID_ANSWER], use_constrained_decoding=False
    )
    assert fake_client.recorded_calls[0].response_json_schema is None


# --- 3. Repair after invalid replies ------------------------------------------------------------
async def test_broken_json_is_repaired_on_second_attempt(composed_prompt):
    broken_reply = '{"summary": "Enterprise customer reports'
    outcome, fake_client = await run_with_replies(composed_prompt, [broken_reply, VALID_ANSWER])

    assert outcome.is_valid and not outcome.first_pass_valid
    assert outcome.attempts_used == 2
    assert outcome.attempts[0].validation_errors[0]["type"] == "json_invalid"
    assert outcome.attempts[1].validation_errors is None

    # The repair turn shows the model its own bad reply, then the error list.
    repair_messages = fake_client.recorded_calls[1].messages
    assert [message["role"] for message in repair_messages] == [
        "system", "user", "assistant", "user",
    ]
    assert repair_messages[2]["content"] == broken_reply
    assert repair_messages[3]["content"].startswith(REPAIR_INSTRUCTION)
    assert "<validation_errors>" in repair_messages[3]["content"]


async def test_business_rule_violation_is_explained_to_the_model(composed_prompt):
    rule_breaking_answer = VALID_ANSWER | {"requires_human_escalation": False}
    _, fake_client = await run_with_replies(composed_prompt, [rule_breaking_answer, VALID_ANSWER])
    repair_text = fake_client.recorded_calls[1].messages[-1]["content"]
    assert "urgency=critical requires requires_human_escalation=true" in repair_text


async def test_error_lines_name_the_field_and_the_bad_value(composed_prompt):
    wrong_enum_answer = VALID_ANSWER | {"urgency": "urgent"}
    _, fake_client = await run_with_replies(composed_prompt, [wrong_enum_answer, VALID_ANSWER])
    repair_text = fake_client.recorded_calls[1].messages[-1]["content"]
    assert "- urgency: Input should be" in repair_text
    assert "(got 'urgent')" in repair_text


async def test_recorded_errors_are_json_serialisable(composed_prompt):
    rule_breaking_answer = VALID_ANSWER | {"requires_human_escalation": False}
    outcome, _ = await run_with_replies(composed_prompt, [rule_breaking_answer, VALID_ANSWER])
    json.dumps(outcome.attempts[0].validation_errors)  # raises TypeError if not


async def test_composed_prompt_is_never_mutated(composed_prompt):
    messages_before = composed_prompt.as_messages()
    await run_with_replies(composed_prompt, ["not json", VALID_ANSWER])
    assert composed_prompt.as_messages() == messages_before


# --- 4. Giving up -------------------------------------------------------------------------------
async def test_gives_up_after_max_repairs(composed_prompt):
    outcome, fake_client = await run_with_replies(
        composed_prompt, ["bad 1", "bad 2", "bad 3"], max_repair_attempts=2
    )
    assert not outcome.is_valid and outcome.parsed_output is None
    assert outcome.attempts_used == 3  # 1 first try + 2 repairs
    assert len(fake_client.recorded_calls) == 3


async def test_zero_repairs_means_a_single_attempt(composed_prompt):
    outcome, _ = await run_with_replies(composed_prompt, ["bad"], max_repair_attempts=0)
    assert not outcome.is_valid and outcome.attempts_used == 1


def test_negative_repair_count_is_rejected():
    with pytest.raises(ValueError):
        StructuredPromptPipeline(ScriptedLLMClient([]), max_repair_attempts=-1)


async def test_truncated_reply_is_recorded(composed_prompt):
    outcome, _ = await run_with_replies(composed_prompt, ['{"summary": "Cut off...', VALID_ANSWER])
    assert outcome.attempts[0].finish_reason == "length"


# --- 5. Bookkeeping and infrastructure errors ---------------------------------------------------
async def test_totals_add_up_across_attempts(composed_prompt):
    outcome, _ = await run_with_replies(composed_prompt, ["bad", VALID_ANSWER])
    assert outcome.total_latency_ms == 200.0  # 2 × 100 ms
    assert outcome.total_tokens == 2 * (1000 + 50)


async def test_transport_errors_propagate_to_the_caller(composed_prompt):
    with pytest.raises(LLMTransportError, match="server down"):
        await run_with_replies(composed_prompt, [LLMTransportError("server down")])
