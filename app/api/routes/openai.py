from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.integrations.deepbridge.engine.auth import LoginRequired
from app.integrations.deepbridge.engine.client import DeepSeekClient

router = APIRouter()
logger = logging.getLogger("goodtogreat.deepbridge")

_client: DeepSeekClient | None = None
_client_lock = threading.Lock()


def _get_client() -> DeepSeekClient:
    """Create one reusable client. Called from a worker thread."""
    global _client

    if _client is not None:
        return _client

    with _client_lock:
        if _client is None:
            _client = DeepSeekClient(allow_interactive=False)
        return _client


def _error(message: str, status: int = 400, kind: str = "invalid_request_error"):
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": kind}},
    )


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


def _messages_to_prompt(messages: list[dict]) -> str:
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

    lines = []
    for role, content in normalized:
        label = {
            "system": "System",
            "developer": "Developer",
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool",
        }.get(role, role.capitalize())
        lines.append(f"{label}: {content}")

    lines.append("Assistant:")
    return "\n\n".join(lines)


def _model_type(model: str) -> str:
    mapping = {
        "deepseek-chat": "default",
        "deepseek-expert": "expert",
        "default": "default",
        "expert": "expert",
    }
    if model not in mapping:
        raise ValueError(
            f"Unsupported model '{model}'. Use deepseek-chat or deepseek-expert."
        )
    return mapping[model]


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


@router.get("/v1/models")
async def list_models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": "deepseek-chat",
                "object": "model",
                "created": now,
                "owned_by": "deepseek",
            },
            {
                "id": "deepseek-expert",
                "object": "model",
                "created": now,
                "owned_by": "deepseek",
            },
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return _error("Request body must be valid JSON.")

    if not isinstance(payload, dict):
        return _error("Request body must be a JSON object.")

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _error("'messages' must be a non-empty array.")

    try:
        prompt = _messages_to_prompt(messages)
    except ValueError as exc:
        return _error(str(exc))

    model = payload.get("model", "deepseek-chat")
    if not isinstance(model, str) or not model:
        return _error("'model' must be a non-empty string.")

    try:
        selected_model = _model_type(model)
    except ValueError as exc:
        return _error(str(exc))

    conversation_id = payload.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        return _error("'conversation_id' must be a string.")

    thinking = payload.get("thinking", False)
    search = payload.get("search", False)
    streaming = payload.get("stream", False)

    if not isinstance(thinking, bool) or not isinstance(search, bool):
        return _error("'thinking' and 'search' must be booleans.")
    if not isinstance(streaming, bool):
        return _error("'stream' must be a boolean.")

    try:
        client = await run_in_threadpool(_get_client)
    except LoginRequired as exc:
        return _error(str(exc), 503, "authentication_error")
    except Exception as exc:
        logger.exception("DeepBridge initialization failed")
        return _error(
            f"DeepBridge initialization failed: {type(exc).__name__}: {exc}",
            503,
            "gateway_error",
        )

    # A resumed conversation retains its original model.
    model_arg = None if conversation_id else selected_model
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())

    if streaming:
        try:
            iterator = client.stream(
                prompt,
                conversation_id=conversation_id,
                model=model_arg,
                thinking=thinking,
                search=search,
            )
        except Exception as exc:
            return _error(
                f"Could not start DeepSeek stream: {exc}",
                502,
                "upstream_error",
            )

        def stream_body():
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }],
            })

            try:
                for text in iterator:
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }],
                    })

                yield _sse({
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "conversation_id": iterator.conversation_id,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                })
            except Exception as exc:
                logger.exception("DeepBridge streaming request failed")
                yield _sse({
                    "error": {
                        "message": str(exc),
                        "type": "upstream_error",
                    }
                })
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        reply = await run_in_threadpool(
            client.chat,
            prompt,
            conversation_id,
            model_arg,
            thinking,
            search,
        )
    except LoginRequired as exc:
        return _error(str(exc), 503, "authentication_error")
    except Exception as exc:
        logger.exception("DeepBridge chat request failed")
        return _error(
            f"DeepSeek request failed: {type(exc).__name__}: {exc}",
            502,
            "upstream_error",
        )

    prompt_tokens = max(1, len(prompt) // 4)
    completion_tokens = max(1, len(reply.text) // 4)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "conversation_id": reply.conversation_id,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": reply.text,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
