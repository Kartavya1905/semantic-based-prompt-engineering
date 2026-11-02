"""
FILE:         src/prompt_engine/schemas/__init__.py
WHAT IT DOES: Package for output contracts (Pydantic models). Manifests point here via
              output_schema_ref, e.g. "prompt_engine.schemas.ticket_triage:TicketTriageResult".
WHERE IT FITS: REGISTERED_CONTRACTS lists every contract whose JSON Schema is snapshot-tested
              (tests/snapshots/<contract_id>_schema.json). CONTRACTS_BY_PROMPT says which
              contracts a prompt's manifests may use. Add new contracts to both.
"""

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from prompt_engine.schemas.ticket_triage import TicketTriageResult
from prompt_engine.schemas.ticket_triage_with_triggers import TicketTriageWithTriggers

ContractT = TypeVar("ContractT", bound=BaseModel)

# --- 1. contract_id → output contract (the id names its snapshot file) ---
REGISTERED_CONTRACTS: dict[str, type[BaseModel]] = {
    "ticket_triage": TicketTriageResult,                          # v1.x: model picks urgency
    "ticket_triage_with_triggers": TicketTriageWithTriggers,      # v2.x: code applies rule 1
}

# --- 1b. prompt_id → contracts its manifests may use (all score against the same dataset) ---
CONTRACTS_BY_PROMPT: dict[str, tuple[type[BaseModel], ...]] = {
    "ticket_triage": (TicketTriageResult, TicketTriageWithTriggers),
}


# --- 2. Canonical text form of a schema, used for snapshots ---
# Key order is preserved (not sorted) on purpose: field order steers generation order,
# so reordering fields is a contract change the snapshot test must catch.
def render_schema_snapshot(contract: type[BaseModel]) -> str:
    return json.dumps(contract.model_json_schema(), indent=2, ensure_ascii=False) + "\n"


# --- 3. Validate any payload by the SAME rules as model output ---
# Contracts are strict, and strict Python-mode validation rejects "technical" for an enum field
# (it wants TicketCategory.TECHNICAL). JSON mode accepts enum values as strings. Few-shot examples
# and golden-dataset answers arrive as dicts from YAML/JSONL, so they go through JSON too.
def validate_as_model_output(contract: type[ContractT], payload: str | dict[str, Any]) -> ContractT:
    json_text = payload if isinstance(payload, str) else json.dumps(payload)
    return contract.model_validate_json(json_text)
