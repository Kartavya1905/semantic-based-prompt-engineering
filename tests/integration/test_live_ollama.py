"""
FILE:         tests/integration/test_live_ollama.py
WHAT IT DOES: End-to-end check against a REAL local model: compose → Ollama → validate.
WHERE IT FITS: Phase 4. Marked "llm", so a plain `pytest` skips it. Run with: pytest -m llm
              Skips itself (instead of failing) when Ollama is not running or the model is missing.
"""

import httpx
import pytest

from prompt_engine.clients.ollama_client import OllamaClient
from prompt_engine.composer import PromptComposer
from prompt_engine.pipeline import StructuredPromptPipeline
from prompt_engine.registry import PromptRegistry
from prompt_engine.schemas.ticket_triage import TicketTriageResult, UrgencyLevel
from prompt_engine.settings import get_settings

pytestmark = pytest.mark.llm

# Unambiguous under policy rule 1 ("full outage of a production service") → must be critical.
FULL_OUTAGE_TICKET = {
    "customer_tier": "pro",
    "ticket_subject": "Whole platform down",
    "ticket_body": (
        "Nobody on our team can load the dashboard or call any API since 10:00. "
        "Production is completely down."
    ),
}
# AMBIGUOUS on purpose: is one failing endpoint a "full outage of a production service" (critical)
# or "a core feature broken for many users" (high)? qwen2.5:7b answers high in every variant
# (checked 2026-11-01). Only assert what holds under BOTH readings: enterprise + high escalates
# (rule 6) and critical escalates (rule 5). Which reading is right is a golden-dataset question.
ENDPOINT_FAILING_TICKET = {
    "customer_tier": "enterprise",
    "ticket_subject": "URGENT: production API returning 500",
    "ticket_body": "Since 09:14 UTC every call to /v2/orders fails with E-5012.",
}


# --- 1. Skip cleanly when the local model is not available --------------------------------------
@pytest.fixture(scope="module")
def live_model_name() -> str:
    settings = get_settings()
    try:
        tags_response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
    except httpx.HTTPError:
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url}")
    pulled_models = {model["name"] for model in tags_response.json().get("models", [])}
    if settings.default_model_name not in pulled_models:
        pytest.skip(f"model not pulled: ollama pull {settings.default_model_name}")
    return settings.default_model_name


async def triage_with_live_model(model_name, variant_label, ticket) -> TicketTriageResult:
    registry = PromptRegistry()
    manifest = registry.load_manifest("ticket_triage", variant_label)
    composed_prompt = PromptComposer(registry).compose(manifest, ticket)
    async with OllamaClient(model_name) as llm_client:
        outcome = await StructuredPromptPipeline(llm_client).run(composed_prompt)
    assert outcome.is_valid, outcome.attempts[-1].raw_text
    assert isinstance(outcome.parsed_output, TicketTriageResult)
    return outcome.parsed_output


VARIANT_LABELS = ["v1_baseline", "v2_policy_first", "v3_fewshot"]


# --- 2. Unambiguous case: a full platform outage is critical and escalates ----------------------
@pytest.mark.parametrize("variant_label", VARIANT_LABELS)
async def test_full_outage_is_critical_and_escalated(live_model_name, variant_label):
    answer = await triage_with_live_model(live_model_name, variant_label, FULL_OUTAGE_TICKET)
    assert answer.urgency is UrgencyLevel.CRITICAL
    assert answer.requires_human_escalation is True


# --- 3. Ambiguous case: check only what every reading of the policy agrees on -------------------
@pytest.mark.parametrize("variant_label", VARIANT_LABELS)
async def test_failing_endpoint_is_urgent_escalated_and_extracted(live_model_name, variant_label):
    answer = await triage_with_live_model(live_model_name, variant_label, ENDPOINT_FAILING_TICKET)
    assert answer.urgency in {UrgencyLevel.HIGH, UrgencyLevel.CRITICAL}
    assert answer.requires_human_escalation is True
    assert "E-5012" in {entity.entity_value for entity in answer.extracted_entities}
