"""
FILE:         src/prompt_engine/clients/ollama_client.py
WHAT IT DOES: Sends chat messages to a local Ollama server (POST /api/chat) and returns a
              CompletionResult. Optionally passes the JSON Schema as "format", which makes Ollama
              constrain decoding so the model can only produce JSON of that shape.
WHERE IT FITS: Phase 4. The default (local) backend behind the LLMClient protocol.
USE:          async with OllamaClient("qwen2.5:7b") as client:
                  result = await client.complete(messages, generation_params, json_schema)
"""

import time
from typing import Any

import httpx

from prompt_engine.clients.base import CompletionResult, LLMTransportError
from prompt_engine.manifest_models import GenerationParams
from prompt_engine.settings import get_settings


class OllamaClient:
    # --- 1. Setup: one reusable HTTP connection pool per client ---------------------------------
    # `transport` lets tests plug in httpx.MockTransport, so no real server is needed.
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model_name = model_name
        self.http_client = httpx.AsyncClient(
            base_url=base_url or get_settings().ollama_base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    # --- 2. Build the request body ---------------------------------------------------------------
    def build_request_payload(
        self,
        messages: list[dict[str, str]],
        generation_params: GenerationParams,
        response_json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sampling_options: dict[str, Any] = {
            "temperature": generation_params.temperature,
            "top_p": generation_params.top_p,
            "num_predict": generation_params.max_output_tokens,  # Ollama's name for max tokens
        }
        if generation_params.seed is not None:
            sampling_options["seed"] = generation_params.seed

        request_payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": sampling_options,
        }
        if response_json_schema is not None:
            request_payload["format"] = response_json_schema  # grammar-constrained decoding
        return request_payload

    # --- 3. One call: send, time it, translate failures into LLMTransportError ------------------
    async def complete(
        self,
        messages: list[dict[str, str]],
        generation_params: GenerationParams,
        response_json_schema: dict[str, Any] | None = None,
    ) -> CompletionResult:
        request_payload = self.build_request_payload(
            messages, generation_params, response_json_schema
        )
        started_at = time.perf_counter()
        try:
            response = await self.http_client.post("/api/chat", json=request_payload)
        except httpx.HTTPError as connection_error:
            raise LLMTransportError(
                f"cannot reach Ollama at {self.http_client.base_url}: {connection_error!r}"
            ) from connection_error
        latency_ms = (time.perf_counter() - started_at) * 1000

        if response.status_code == 404:
            raise LLMTransportError(
                f"model {self.model_name!r} not found - run: ollama pull {self.model_name}"
            )
        if response.is_error:
            raise LLMTransportError(f"Ollama returned HTTP {response.status_code}: {response.text}")

        # --- 4. Parse the reply (token counts are absent on some cached responses) --------------
        # A reply that is not Ollama's JSON (e.g. a proxy's HTML error page) is a server problem,
        # not a bad answer: raising LLMTransportError lets the benchmark record it and resume.
        try:
            response_body = response.json()
            raw_text = response_body["message"]["content"]
        except (ValueError, KeyError, TypeError) as parse_error:
            raise LLMTransportError(
                f"unexpected reply from Ollama: {response.text[:200]!r}"
            ) from parse_error
        return CompletionResult(
            raw_text=raw_text,
            latency_ms=latency_ms,
            prompt_tokens=response_body.get("prompt_eval_count", 0),
            completion_tokens=response_body.get("eval_count", 0),
            finish_reason=response_body.get("done_reason", "stop"),
            model_name=self.model_name,
        )

    # --- 5. Cleanup: close the connection pool --------------------------------------------------
    async def aclose(self) -> None:
        await self.http_client.aclose()

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *exception_info: object) -> None:
        await self.aclose()
