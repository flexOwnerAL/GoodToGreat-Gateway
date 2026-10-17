"""OpenAI-compatible API routes.

All /v1/* endpoints live here. Routing logic:
  1. DeepBridge models (deepseek-chat, deepseek-expert) — handled directly via
     the existing DeepSeekClient, which is not a BaseProvider subclass (by design,
     to keep it unchanged).
  2. All other models (g4f:*, ollama:*, gptbridge-free) — routed through the
     ProviderRegistry with automatic fallback on transient errors.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.integrations.deepbridge.engine.auth import LoginRequired
from app.integrations.deepbridge.engine.client import DeepSeekClient
from app.core.config import get_settings
from app.providers import registry
from app.utils.tokens import usage_block

router = APIRouter()
logger = logging.getLogger("goodtogreat.routes")
SYSTEM_FINGERPRINT = "fp_gtg_gateway"

# ---------------------------------------------------------------------------
# DeepBridge client (singleton, lazily created in a thread)
# ---------------------------------------------------------------------------
_db_client: DeepSeekClient | None = None
_db_lock = threading.Lock()


def _get_deepbridge_client() -> DeepSeekClient:
    global _db_client
    if _db_client is not None:
        return _db_client
    with _db_lock:
        if _db_client is None:
            _db_client = DeepSeekClient(allow_interactive=False)
        return _db_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(
    message: str,
    status: int = 400,
    kind: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": kind, "param": param, "code": code}},
    )


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _messages_to_deepbridge_prompt(messages: list[dict]) -> str:
    """Convert OpenAI messages list to a single prompt string for DeepBridge."""
    normalized = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Every messages entry must be an object.")
        role = message.get("role")
        if not isinstance(role, str) or not role.strip():
            raise ValueError("Every message needs a non-empty role.")
        content = _content_text(message.get("content"))
        normalized.append((role.strip().lower(), content))

    if len(normalized) == 1 and normalized[0][0] == "user":
        return normalized[0][1]

    labels = {"system": "System", "developer": "Developer", "user": "User",
              "assistant": "Assistant", "tool": "Tool"}
    lines = [f"{labels.get(role, role.capitalize())}: {content}" for role, content in normalized]
    lines.append("Assistant:")
    return "\n\n".join(lines)


def _deepbridge_model_type(model: str) -> str:
    mapping = {"deepseek-chat": "default", "deepseek-expert": "expert",
               "default": "default", "expert": "expert"}
    if model not in mapping:
        raise ValueError(f"Unsupported model '{model}'. Use deepseek-chat or deepseek-expert.")
    return mapping[model]


def _is_deepbridge(model: str) -> bool:
    return model in ("deepseek-chat", "deepseek-expert", "default", "expert")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/v1/models")
async def list_models():
    now = int(time.time())
    # DeepBridge models are always present.
    data: list[dict] = [
        {"id": "deepseek-chat", "object": "model", "created": now, "owned_by": "deepseek"},
        {"id": "deepseek-expert", "object": "model", "created": now, "owned_by": "deepseek"},
    ]
    # Add all registry-managed provider models.
    data.extend(await registry.list_all_models())
    return {"object": "list", "data": data}


@router.get("/v1/models/{model_id:path}")
async def retrieve_model(model_id: str):
    listing = await list_models()
    for model in listing["data"]:
        if model["id"] == model_id:
            return model
    return _error(
        f"Model '{model_id}' does not exist or is not available.",
        404, "invalid_request_error", param="model", code="model_not_found",
    )


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # --- Parse & validate -----------------------------------------------
    try:
        payload = await request.json()
    except Exception:
        return _error("Request body must be valid JSON.")

    if not isinstance(payload, dict):
        return _error("Request body must be a JSON object.")

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _error("'messages' must be a non-empty array.")

    model = payload.get("model", "deepseek-chat")
    if not isinstance(model, str) or not model:
        return _error("'model' must be a non-empty string.")

    n = payload.get("n", 1)
    if not isinstance(n, int) or n != 1:
        return _error(
            "Only n=1 is supported: providers return one completion per request.",
            400, "invalid_request_error", param="n", code="unsupported_value",
        )

    streaming = payload.get("stream", False)
    if not isinstance(streaming, bool):
        return _error("'stream' must be a boolean.")

    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())

    # --- DeepBridge path ------------------------------------------------
    if _is_deepbridge(model):
        try:
            prompt = _messages_to_deepbridge_prompt(messages)
        except ValueError as exc:
            return _error(str(exc))

        thinking = payload.get("thinking", False)
        search = payload.get("search", False)
        if not isinstance(thinking, bool) or not isinstance(search, bool):
            return _error("'thinking' and 'search' must be booleans.")

        conversation_id = payload.get("conversation_id")
        if conversation_id is not None and not isinstance(conversation_id, str):
            return _error("'conversation_id' must be a string.")

        try:
            client = await run_in_threadpool(_get_deepbridge_client)
        except LoginRequired as exc:
            return _error(str(exc), 503, "authentication_error")
        except Exception as exc:
            logger.exception("DeepBridge initialization failed")
            return _error(f"DeepBridge initialization failed: {type(exc).__name__}: {exc}", 503, "gateway_error")

        model_arg = None if conversation_id else _deepbridge_model_type(model)

        if streaming:
            try:
                iterator = client.stream(prompt, conversation_id=conversation_id,
                                         model=model_arg, thinking=thinking, search=search)
            except Exception as exc:
                return _error(f"Could not start DeepSeek stream: {exc}", 502, "upstream_error")

            def _deepbridge_stream():
                yield _sse({"id": completion_id, "object": "chat.completion.chunk",
                            "created": created, "model": model,
                            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
                try:
                    for text in iterator:
                        yield _sse({"id": completion_id, "object": "chat.completion.chunk",
                                    "created": created, "model": model,
                                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]})
                    yield _sse({"id": completion_id, "object": "chat.completion.chunk",
                                "created": created, "model": model,
                                "conversation_id": iterator.conversation_id,
                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                except Exception as exc:
                    logger.exception("DeepBridge streaming failed")
                    yield _sse({"error": {"message": str(exc), "type": "upstream_error"}})
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(_deepbridge_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        try:
            reply = await run_in_threadpool(client.chat, prompt, conversation_id, model_arg, thinking, search)
        except LoginRequired as exc:
            return _error(str(exc), 503, "authentication_error")
        except Exception as exc:
            logger.exception("DeepBridge chat failed")
            return _error(f"DeepSeek request failed: {type(exc).__name__}: {exc}", 502, "upstream_error")

        return {
            "id": completion_id, "object": "chat.completion", "created": created, "model": model,
            "system_fingerprint": SYSTEM_FINGERPRINT,
            "conversation_id": reply.conversation_id,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply.text}, "finish_reason": "stop"}],
            "usage": usage_block(prompt, reply.text),
        }

    # --- Registry path (g4f, ollama, gptbridge) --------------------------
    provider = registry.resolve_provider(model)
    if provider is None:
        # Try fallback chain: attempt each registered provider in priority order.
        return await _fallback_chat(model, messages, payload, completion_id, created, streaming)

    return await _provider_chat(provider, model, messages, payload, completion_id, created, streaming)


async def _provider_chat(
    provider,
    model: str,
    messages: list[dict],
    payload: dict,
    completion_id: str,
    created: int,
    streaming: bool,
) -> Any:
    """Route a request to a specific provider."""
    options = {k: payload[k] for k in ("temperature", "top_p", "seed") if k in payload}

    if streaming:
        async def _stream_body():
            yield _sse({"id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": model, "system_fingerprint": SYSTEM_FINGERPRINT,
                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
            try:
                async for chunk in provider.stream(model, messages, **options):
                    yield _sse({"id": completion_id, "object": "chat.completion.chunk",
                                "created": created, "model": model,
                                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]})
                yield _sse({"id": completion_id, "object": "chat.completion.chunk",
                            "created": created, "model": model,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            except httpx.TimeoutException:
                logger.warning("Provider timeout for model %s", model)
                yield _sse({"error": {"message": "Provider request timed out.", "type": "upstream_timeout"}})
            except httpx.HTTPStatusError as exc:
                logger.warning("Provider HTTP %s for model %s", exc.response.status_code, model)
                yield _sse({"error": {"message": "Provider rejected the request.", "type": "upstream_error"}})
            except httpx.HTTPError:
                logger.warning("Provider connection failed for model %s", model)
                yield _sse({"error": {"message": "Provider is unavailable.", "type": "upstream_error"}})
            except Exception:
                logger.exception("Provider stream failed for model %s", model)
                yield _sse({"error": {"message": "Provider request failed.", "type": "upstream_error"}})
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(_stream_body(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    try:
        result = await provider.generate(model, messages, **options)
    except httpx.TimeoutException:
        return _error("Provider request timed out.", 504, "upstream_timeout")
    except httpx.HTTPStatusError as exc:
        logger.warning("Provider HTTP error %s for model %s", exc.response.status_code, model)
        return _error("Provider rejected the request.", 502, "upstream_error")
    except httpx.HTTPError:
        logger.warning("Provider connection failed for model %s", model)
        return _error("Provider is unavailable. Check its local service and URL.", 503, "provider_unavailable")
    except Exception:
        logger.exception("Provider request failed for model %s", model)
        return _error("Provider request failed.", 502, "upstream_error")

    choices = result.get("choices", [])
    usage = result.get("usage", usage_block("", ""))
    return {
        "id": completion_id, "object": "chat.completion", "created": created, "model": model,
        "system_fingerprint": SYSTEM_FINGERPRINT,
        "choices": choices,
        "usage": usage,
    }


async def _fallback_chat(
    model: str,
    messages: list[dict],
    payload: dict,
    completion_id: str,
    created: int,
    streaming: bool,
) -> Any:
    """Try every provider in priority order until one succeeds.

    This is used when model='auto' or an unknown model is requested.
    If all providers fail, return a 503.
    """
    options = {k: payload[k] for k in ("temperature", "top_p", "seed") if k in payload}
    last_error: str = "No providers available."

    for pname in registry.priority_order():
        try:
            provider = registry.get(pname)
        except LookupError:
            continue

        # For fallback, use the first model each provider exposes.
        try:
            models = await provider.list_models()
        except Exception:
            continue
        if not models:
            continue

        fallback_model = models[0]["id"]
        logger.info("Fallback: trying provider=%s model=%s for requested model=%s", pname, fallback_model, model)

        try:
            result = await provider.generate(fallback_model, messages, **options)
            choices = result.get("choices", [])
            usage = result.get("usage", usage_block("", ""))
            return {
                "id": completion_id, "object": "chat.completion", "created": created,
                "model": fallback_model,
                "system_fingerprint": SYSTEM_FINGERPRINT,
                "x_fallback_note": f"Requested model '{model}' not found; served by {pname}.",
                "choices": choices,
                "usage": usage,
            }
        except Exception as exc:
            last_error = f"{pname}: {exc}"
            logger.warning("Fallback provider %s failed: %s", pname, exc)
            continue

    return _error(
        f"Model '{model}' is not available and all fallback providers failed. Last error: {last_error}",
        503, "provider_unavailable",
    )
