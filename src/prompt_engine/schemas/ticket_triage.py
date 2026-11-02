"""
FILE:         src/prompt_engine/schemas/ticket_triage.py
WHAT IT DOES: The output contract for the ticket_triage prompt — the exact shape, allowed values
              and business rules every model answer must satisfy.
WHERE IT FITS: Written FIRST (Phase 1): the composer injects its JSON Schema into the prompt
              (Phase 3), the pipeline validates answers against it (Phase 4), and the metrics
              compare its fields to the golden dataset (Phase 6).
USED BY:      manifests, via output_schema_ref
              "prompt_engine.schemas.ticket_triage:TicketTriageResult"
VERSIONING:   Any change here changes the JSON Schema → update the snapshot
              (python scripts/update_schema_snapshots.py) AND bump the manifests' MAJOR version.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"


# --- 1. Closed vocabularies: enums become "enum": [...] in the JSON Schema ----------------------
# Constrained decoding can then only emit these exact strings.
class TicketCategory(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class UrgencyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EntityType(StrEnum):
    PRODUCT = "product"
    ORDER_ID = "order_id"
    INVOICE_ID = "invoice_id"
    ERROR_CODE = "error_code"


# --- 2. Shared strictness for every model in this contract ---------------------------------------
# extra="forbid"            → "additionalProperties": false; unknown keys are errors, not ignored
# strict=True               → no type coercion: "yes"/"1" are NOT booleans, "0.9" is NOT a number.
#                             Lax mode would silently "fix" sloppy output and hide prompt defects.
# str_strip_whitespace=True → "  E-5012 " and "E-5012" are the same value
STRICT_CONTRACT_CONFIG = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


# --- 3. Nested object: one identifier copied from the ticket -------------------------------------
class ExtractedEntity(BaseModel):
    model_config = STRICT_CONTRACT_CONFIG

    entity_type: EntityType = Field(description="Kind of identifier.")
    entity_value: str = Field(
        min_length=1,
        max_length=100,
        description="The identifier exactly as written in the ticket. Never invented.",
    )


# --- 4. The top-level contract -------------------------------------------------------------------
# Field ORDER is deliberate: JSON Schema keeps declaration order, and the model generates fields
# in that order. Evidence (summary, entities) comes before decisions (category, urgency, escalation)
# so each decision is conditioned on text the model has already written.
class TicketTriageResult(BaseModel):
    """Structured triage decision for one customer support ticket."""

    model_config = ConfigDict(
        **STRICT_CONTRACT_CONFIG,
        title="TicketTriageResult",
        json_schema_extra={"x-schema-version": SCHEMA_VERSION},
    )

    summary: str = Field(
        min_length=10,
        max_length=280,
        description="One third-person sentence stating the issue, with concrete identifiers.",
    )
    # No default on purpose: every field is "required", so the output shape never varies and
    # the model must state "no entities" explicitly as [] instead of silently omitting the key.
    extracted_entities: list[ExtractedEntity] = Field(
        max_length=10,
        description="Identifiers literally present in the ticket; empty list if none.",
    )
    category: TicketCategory = Field(description="The single dominant issue type.")
    urgency: UrgencyLevel = Field(description="Business impact and time sensitivity.")
    requires_human_escalation: bool = Field(
        description="True if a human must review before any automated response."
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated probability that category AND urgency are both correct.",
    )

    # --- 5. Business rules: cross-field logic that constrained decoding cannot enforce ----------
    # A ValueError here becomes a ValidationError, which the Phase 4 repair loop feeds back
    # to the model as <validation_errors>.
    @model_validator(mode="after")
    def critical_tickets_must_escalate(self) -> "TicketTriageResult":
        if self.urgency is UrgencyLevel.CRITICAL and not self.requires_human_escalation:
            raise ValueError("urgency=critical requires requires_human_escalation=true")
        return self

    @model_validator(mode="after")
    def entities_must_be_unique(self) -> "TicketTriageResult":
        check_entities_unique(self.extracted_entities)
        return self


# --- 6. Shared rule, also used by the v2 contract (ticket_triage_with_triggers.py) --------------
def check_entities_unique(extracted_entities: list[ExtractedEntity]) -> None:
    entity_keys = [
        (entity.entity_type, entity.entity_value.lower()) for entity in extracted_entities
    ]
    if len(entity_keys) != len(set(entity_keys)):
        raise ValueError("extracted_entities contains duplicates (same type and value)")
