"""
FILE:         tests/fakes.py
WHAT IT DOES: A scripted stand-in for a real model. It replies with pre-written answers in order
              and records every call, so pipeline logic can be tested exactly and offline.
USED BY:      tests/unit/test_pipeline.py (and the benchmark tests in Phase 6)
"""

import json
from dataclasses import dataclass, field
from typing import Any

from prompt_engine.clients.base import CompletionResult, LLMTransportError
from prompt_engine.manifest_models import GenerationParams


@dataclass
class RecordedCall:
    messages: list[dict[str, str]]
    generation_params: GenerationParams
    response_json_schema: dict[str, Any] | None


@dataclass
class ScriptedLLMClient:
    """Each scripted reply is a str (sent as-is), a dict (sent as JSON) or an exception (raised)."""

    scripted_replies: list[str | dict[str, Any] | Exception]
    model_name: str = "scripted-fake"
    latency_ms_per_call: float = 100.0
    recorded_calls: list[RecordedCall] = field(default_factory=list)
    is_closed: bool = False

    async def complete(
        self,
        messages: list[dict[str, str]],
        generation_params: GenerationParams,
        response_json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        self.recorded_calls.append(
            RecordedCall([dict(message) for message in messages], generation_params,
                         response_json_schema)
        )
        if not self.scripted_replies:
            raise AssertionError("ScriptedLLMClient ran out of scripted replies")
        next_reply = self.scripted_replies.pop(0)
        if isinstance(next_reply, Exception):
            raise next_reply
        raw_text = next_reply if isinstance(next_reply, str) else json.dumps(next_reply)
        return CompletionResult(
            raw_text=raw_text,
            latency_ms=self.latency_ms_per_call,
            prompt_tokens=1000,
            completion_tokens=50,
            finish_reason="length" if raw_text.endswith("...") else "stop",
            model_name=self.model_name,
        )

    async def aclose(self) -> None:
        self.is_closed = True


@dataclass
class OracleLLMClient:
    """Answers each ticket by looking it up: a fake 'perfect model' for benchmark tests.

    answers_by_body maps ticket_body → answer dict. Bodies in broken_first_reply_bodies get a
    broken first reply (so the repair loop runs). always_fail raises LLMTransportError every call.
    """

    answers_by_body: dict[str, dict[str, Any]]
    model_name: str = "oracle-fake"
    broken_first_reply_bodies: set[str] = field(default_factory=set)
    always_fail: bool = False
    call_count: int = 0
    events: list[tuple[str, str]] | None = None  # shared log of ("call"/"close", model_name)

    async def complete(
        self,
        messages: list[dict[str, str]],
        generation_params: GenerationParams,
        response_json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        from prompt_engine.templating import xml_safe

        self.call_count += 1
        if self.events is not None:
            self.events.append(("call", self.model_name))
        if self.always_fail:
            raise LLMTransportError("oracle server down")

        human_message = messages[1]["content"]
        ticket_body = next(
            body for body in self.answers_by_body if xml_safe(body) in human_message
        )
        is_first_attempt = len(messages) == 2
        if is_first_attempt and ticket_body in self.broken_first_reply_bodies:
            raw_text = '{"summary": "broken'
        else:
            raw_text = json.dumps(self.answers_by_body[ticket_body])
        return CompletionResult(raw_text, 50.0, 1000, 60, "stop", self.model_name)

    async def aclose(self) -> None:
        if self.events is not None:
            self.events.append(("close", self.model_name))


__all__ = ["LLMTransportError", "OracleLLMClient", "RecordedCall", "ScriptedLLMClient"]
