"""
FILE:         tests/unit/test_ollama_client.py
WHAT IT DOES: Checks the Ollama client builds the right request and reads the reply correctly,
              using httpx.MockTransport in place of a real server.
WHERE IT FITS: Phase 4. Offline. tests/integration/test_live_ollama.py covers the real server.
"""

import json

import httpx
import pytest

from prompt_engine.clients.base import LLMTransportError
from prompt_engine.clients.ollama_client import OllamaClient
from prompt_engine.manifest_models import GenerationParams

MESSAGES = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
OLLAMA_REPLY = {
    "model": "qwen2.5:7b",
    "message": {"role": "assistant", "content": '{"ok": true}'},
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 120,
    "eval_count": 8,
}


# --- 1. A fake server that records what it receives ---------------------------------------------
def build_client(status_code=200, reply_body=None, captured_requests=None) -> OllamaClient:
    def handle_request(request: httpx.Request) -> httpx.Response:
        if captured_requests is not None:
            captured_requests.append(request)
        response_body = reply_body if reply_body is not None else OLLAMA_REPLY
        return httpx.Response(status_code, json=response_body)

    return OllamaClient(
        "qwen2.5:7b", base_url="http://ollama.test", transport=httpx.MockTransport(handle_request)
    )


# --- 2. Request payload -------------------------------------------------------------------------
async def test_request_payload_maps_every_parameter():
    captured_requests: list[httpx.Request] = []
    generation_params = GenerationParams(
        temperature=0.3, top_p=0.9, seed=7, max_output_tokens=256
    )
    async with build_client(captured_requests=captured_requests) as client:
        await client.complete(MESSAGES, generation_params, {"type": "object"})

    sent_request = captured_requests[0]
    assert sent_request.url.path == "/api/chat"
    sent_payload = json.loads(sent_request.content)
    assert sent_payload == {
        "model": "qwen2.5:7b",
        "messages": MESSAGES,
        "stream": False,
        "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 256, "seed": 7},
        "format": {"type": "object"},
    }


async def test_no_seed_and_no_schema_are_left_out_of_the_payload():
    captured_requests: list[httpx.Request] = []
    async with build_client(captured_requests=captured_requests) as client:
        await client.complete(MESSAGES, GenerationParams(temperature=0.0))
    sent_payload = json.loads(captured_requests[0].content)
    assert "seed" not in sent_payload["options"]
    assert "format" not in sent_payload


# --- 3. Reply parsing ---------------------------------------------------------------------------
async def test_reply_is_parsed_into_a_completion_result():
    async with build_client() as client:
        result = await client.complete(MESSAGES, GenerationParams(temperature=0.0))
    assert result.raw_text == '{"ok": true}'
    assert (result.prompt_tokens, result.completion_tokens) == (120, 8)
    assert result.finish_reason == "stop"
    assert result.model_name == "qwen2.5:7b"
    assert result.latency_ms >= 0


async def test_missing_token_counts_default_to_zero():
    sparse_reply = {"message": {"role": "assistant", "content": "{}"}, "done": True}
    async with build_client(reply_body=sparse_reply) as client:
        result = await client.complete(MESSAGES, GenerationParams(temperature=0.0))
    assert (result.prompt_tokens, result.completion_tokens, result.finish_reason) == (0, 0, "stop")


# --- 4. Failures become LLMTransportError, with an actionable message ---------------------------
async def test_model_not_pulled_explains_the_fix():
    async with build_client(status_code=404, reply_body={"error": "model not found"}) as client:
        with pytest.raises(LLMTransportError, match="ollama pull qwen2.5:7b"):
            await client.complete(MESSAGES, GenerationParams(temperature=0.0))


async def test_server_error_is_a_transport_error():
    async with build_client(status_code=500, reply_body={"error": "out of memory"}) as client:
        with pytest.raises(LLMTransportError, match="HTTP 500"):
            await client.complete(MESSAGES, GenerationParams(temperature=0.0))


async def test_unreachable_server_is_a_transport_error():
    def refuse_connection(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient("qwen2.5:7b", base_url="http://ollama.test",
                          transport=httpx.MockTransport(refuse_connection))
    async with client:
        with pytest.raises(LLMTransportError, match="cannot reach Ollama"):
            await client.complete(MESSAGES, GenerationParams(temperature=0.0))
