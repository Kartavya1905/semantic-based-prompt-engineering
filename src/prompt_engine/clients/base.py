"""
FILE:         src/prompt_engine/clients/base.py
WHAT IT DOES: The contract every LLM backend must follow (LLMClient), the result it returns
              (CompletionResult), and the one error type for infrastructure failures.
WHERE IT FITS: Phase 4. The pipeline only knows this protocol, so swapping or faking a backend
              (tests use a scripted fake) never touches pipeline code.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from prompt_engine.manifest_models import GenerationParams


# --- 1. What one model call returns ------------------------------------------------------------
@dataclass(frozen=True)
class CompletionResult:
    raw_text: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    # "stop" = the model finished; "length" = cut off by max_output_tokens (usually broken JSON).
    finish_reason: str
    model_name: str


# --- 2. Infrastructure failures (server down, timeout, model not pulled) -----------------------
# Kept separate from bad ANSWERS on purpose: the benchmark excludes these from quality metrics,
# because a timeout says nothing about how good a prompt is.
class LLMTransportError(Exception):
    pass


# --- 3. The protocol: any class with these members is a valid backend ---------------------------
class LLMClient(Protocol):
    model_name: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        generation_params: GenerationParams,
        response_json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult: ...

    async def aclose(self) -> None: ...
