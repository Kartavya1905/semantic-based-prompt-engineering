"""
FILE:         src/prompt_engine/schemas/ticket_triage_with_triggers.py
WHAT IT DOES: Output contract v2 for ticket_triage. The model ALSO answers three factual yes/no
              questions (the critical triggers). Then CODE, not the model, applies urgency rule 1:
              any trigger true → urgency=critical and escalation=true.
WHY:          In 1,188 dev runs qwen2.5:7b never chose "critical" by its own judgement; it only
              repeated the word when a ticket demanded it (prompt injection). Rewording the policy
              did not help (critical_fix experiment, 2026-11-02). Small models are usually better
              at answering factual questions than at applying a ranking rule.
WHERE IT FITS: Used by manifest v6_critical_triggers. The v1 contract (ticket_triage.py) stays
              unchanged, so v1-v5 results remain comparable. The golden dataset is unchanged:
              final urgency/escalation are scored exactly as before.
VERSIONING:   SCHEMA_VERSION 2.x.x → manifests using this contract must be version 2.x.x.
              MAJOR = the shape changes (fields, types, order); MINOR = wording only.
              2.1.0 (2026-11-02): full_outage_reported narrowed to a WHOLE service/product/
              endpoint, matching annotation guideline C1/C1b.
"""

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from prompt_engine.schemas.ticket_triage import (
    STRICT_CONTRACT_CONFIG,
    ExtractedEntity,
    TicketCategory,
    UrgencyLevel,
    check_entities_unique,
)

SCHEMA_VERSION = "2.1.0"


class TicketTriageWithTriggers(BaseModel):
    """Triage decision where critical urgency is derived from three reported facts."""

    model_config = ConfigDict(
        **STRICT_CONTRACT_CONFIG,
        title="TicketTriageWithTriggers",
        json_schema_extra={"x-schema-version": SCHEMA_VERSION},
    )

    # --- 1. Evidence (as in v1) ------------------------------------------------------------------
    summary: str = Field(
        min_length=10,
        max_length=280,
        description="One third-person sentence stating the issue, with concrete identifiers.",
    )
    extracted_entities: list[ExtractedEntity] = Field(
        max_length=10,
        description="Identifiers literally present in the ticket; empty list if none.",
    )

    # --- 2. NEW: the critical triggers, answered as facts BEFORE any urgency decision ------------
    data_loss_reported: bool = Field(
        description="True if the ticket reports records, files or history deleted, overwritten "
        "or missing."
    )
    security_exposure_reported: bool = Field(
        description="True if passwords, keys or tokens were shown or leaked, data was visible to "
        "people who should not see it, or someone accessed an account without authorisation."
    )
    full_outage_reported: bool = Field(
        description="True only if a WHOLE production service, product or API endpoint is "
        "unavailable: nothing loads, or every call fails. False if one function fails while the "
        "rest of the product still works."
    )

    # --- 3. Decisions (as in v1) -----------------------------------------------------------------
    category: TicketCategory = Field(description="The single dominant issue type.")
    urgency: UrgencyLevel = Field(
        description="Business impact. Must be critical if any *_reported field is true, and "
        "only then."
    )
    requires_human_escalation: bool = Field(
        description="True if a human must review before any automated response."
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated probability that category AND urgency are both correct.",
    )

    # What the model itself chose, before rule 1 was applied (not part of the JSON Schema).
    _model_proposed_urgency: UrgencyLevel | None = PrivateAttr(default=None)

    # --- 4. Rule 1 in code ------------------------------------------------------------------
    @model_validator(mode="after")
    def apply_critical_rule(self) -> "TicketTriageWithTriggers":
        check_entities_unique(self.extracted_entities)
        self._model_proposed_urgency = self.urgency
        if self.critical_trigger_found:
            # 4a. A reported fact makes it critical, whatever urgency the model picked.
            self.urgency = UrgencyLevel.CRITICAL
            self.requires_human_escalation = True  # rule 5
        elif self.urgency is UrgencyLevel.CRITICAL:
            # 4b. "critical" with no reported fact (e.g. a ticket demanding it) is inconsistent:
            # raising sends the answer through the repair loop instead of trusting the word.
            raise ValueError(
                "urgency=critical requires data_loss_reported, security_exposure_reported or "
                "full_outage_reported to be true"
            )
        return self

    # --- 5. Read-only facts for evaluation --------------------------------------------------
    @property
    def critical_trigger_found(self) -> bool:
        return (
            self.data_loss_reported
            or self.security_exposure_reported
            or self.full_outage_reported
        )

    @property
    def model_proposed_urgency(self) -> UrgencyLevel | None:
        return self._model_proposed_urgency

    @property
    def urgency_set_by_rule(self) -> bool:
        """True when code raised the urgency to critical over the model's own choice."""
        return self.urgency is UrgencyLevel.CRITICAL and (
            self._model_proposed_urgency is not UrgencyLevel.CRITICAL
        )
