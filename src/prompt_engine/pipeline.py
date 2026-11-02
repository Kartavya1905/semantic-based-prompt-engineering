"""
FILE:         src/prompt_engine/pipeline.py
WHAT IT DOES: The guardrail loop: send the composed prompt → validate the answer against the
              output contract → if invalid, show the model its errors and ask again → stop when
              valid or out of attempts.
WHERE IT FITS: Phase 4. Sits between the composer (Phase 3) and the benchmark (Phase 6).
              Every attempt is recorded, so evaluation can tell a prompt that is right the FIRST
              time from one that only gets there after repairs.

  composed prompt ──► model ──► validate ──► valid? ──yes──► PipelineOutcome(is_valid=True)
                        ▲                      │ no
                        └── <validation_errors> ◄┘   (up to max_repair_attempts times)
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from prompt_engine.clients.base import LLMClient
from prompt_engine.composer import ComposedPrompt

REPAIR_INSTRUCTION = (
    "Your previous reply did not match <output_schema>. Fix every problem listed below and "
    "reply with the corrected JSON object only."
)


# --- 1. What happened on one attempt -----------------------------------------------------------
@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    raw_text: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    validation_errors: list[dict[str, Any]] | None  # None = this attempt was valid


# --- 2. The overall result, with the numbers evaluation needs ----------------------------------
@dataclass
class PipelineOutcome:
    prompt_fingerprint: str
    parsed_output: BaseModel | None = None
    attempts: list[AttemptRecord] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.parsed_output is not None

    @property
    def attempts_used(self) -> int:
        return len(self.attempts)

    @property
    def first_pass_valid(self) -> bool:
        """Valid with NO repair: the honest measure of prompt quality."""
        return self.is_valid and self.attempts_used == 1

    @property
    def total_latency_ms(self) -> float:
        return sum(attempt.latency_ms for attempt in self.attempts)

    @property
    def total_tokens(self) -> int:
        return sum(attempt.prompt_tokens + attempt.completion_tokens for attempt in self.attempts)


# --- 3. Turn Pydantic errors into short lines a model can act on -------------------------------
# e.g. "- urgency: Input should be 'low', 'medium', 'high' or 'critical' (got 'urgent')"
def format_errors_for_model(validation_error: ValidationError) -> str:
    error_lines = []
    for error in validation_error.errors(include_url=False):
        field_path = ".".join(str(part) for part in error["loc"]) or "(whole object)"
        received_value = repr(error.get("input"))
        if len(received_value) > 80:
            received_value = received_value[:77] + "..."
        error_lines.append(f"- {field_path}: {error['msg']} (got {received_value})")
    return "\n".join(error_lines)


# Business-rule errors carry the raw ValueError in "ctx", which cannot be written to the JSONL
# results files (Phase 6). Dropping ctx keeps type, loc, msg and input: all plain JSON values.
def json_safe_errors(validation_error: ValidationError | None) -> list[dict[str, Any]] | None:
    if validation_error is None:
        return None
    return [
        dict(error) for error in validation_error.errors(include_url=False, include_context=False)
    ]


class StructuredPromptPipeline:
    # --- 4. Setup --------------------------------------------------------------------------------
    # use_constrained_decoding=False sends no schema to the server, so the model is free to break
    # the format: useful as an ablation ("how much does constrained decoding buy us?").
    def __init__(
        self,
        llm_client: LLMClient,
        max_repair_attempts: int = 2,
        use_constrained_decoding: bool = True,
    ) -> None:
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be >= 0")
        self.llm_client = llm_client
        self.max_repair_attempts = max_repair_attempts
        self.use_constrained_decoding = use_constrained_decoding

    # --- 5. The loop ------------------------------------------------------------------------------
    # LLMTransportError is NOT caught here: an unreachable server is not a bad answer, and the
    # caller (benchmark) records it separately.
    async def run(self, composed_prompt: ComposedPrompt) -> PipelineOutcome:
        output_schema = composed_prompt.output_schema
        response_json_schema = (
            output_schema.model_json_schema() if self.use_constrained_decoding else None
        )
        conversation = composed_prompt.as_messages()  # a fresh list; the prompt is never mutated
        outcome = PipelineOutcome(prompt_fingerprint=composed_prompt.prompt_fingerprint)

        for attempt_number in range(1, self.max_repair_attempts + 2):
            completion = await self.llm_client.complete(
                conversation, composed_prompt.generation_params, response_json_schema
            )

            # 5a. Validate. Broken JSON and wrong content both raise ValidationError.
            try:
                parsed_output: BaseModel | None = output_schema.model_validate_json(
                    completion.raw_text
                )
                validation_error = None
            except ValidationError as caught_error:
                parsed_output, validation_error = None, caught_error

            outcome.attempts.append(
                AttemptRecord(
                    attempt_number=attempt_number,
                    raw_text=completion.raw_text,
                    latency_ms=completion.latency_ms,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                    finish_reason=completion.finish_reason,
                    validation_errors=json_safe_errors(validation_error),
                )
            )

            # 5b. Valid → done.
            if parsed_output is not None:
                outcome.parsed_output = parsed_output
                return outcome

            # 5c. Invalid → show the model its own answer plus the error list, then try again.
            assert validation_error is not None
            conversation = conversation + [
                {"role": "assistant", "content": completion.raw_text},
                {
                    "role": "user",
                    "content": (
                        f"{REPAIR_INSTRUCTION}\n\n<validation_errors>\n"
                        f"{format_errors_for_model(validation_error)}\n</validation_errors>"
                    ),
                },
            ]

        # 5d. Out of attempts: parsed_output stays None, so the caller abstains / asks a human.
        return outcome
