"""Ollama local model provider."""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider
from app.utils.tokens import usage_block


class OllamaProvider(BaseProvider):
    name = "ollama"

    def _base_url(self) -> str:
        return get_settings().ollama_base_url.rstrip("/")

    def _timeout(self) -> float:
        return get_settings().ollama_timeout_seconds

    async def list_models(self) -> list[dict[str, Any]]:
        if not get_settings().ollama_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url()}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
            now = int(time.time())
            return [
                {
                    "id": f"ollama:{m['name']}",
                    "object": "model",
                    "created": now,
                    "owned_by": "ollama",
                }
                for m in models
                if isinstance(m, dict) and isinstance(m.get("name"), str)
            ]
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        raw_model = model.removeprefix("ollama:")
        body: dict[str, Any] = {
            "model": raw_model,
            "messages": [
                {"role": m.get("role", "user"), "content": _content_text(m.get("content"))}
                for m in messages
            ],
            "stream": False,
        }
        opts = {k: options[k] for k in ("temperature", "top_p", "seed") if k in options}
        if opts:
            body["options"] = opts

        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            response = await client.post(f"{self._base_url()}/api/chat", json=body)
            response.raise_for_status()
            data = response.json()

        content = str(data.get("message", {}).get("content", ""))
        prompt_str = " ".join(_content_text(m.get("content")) for m in messages)
        return {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": usage_block(prompt_str, content),
        }

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> AsyncIterator[str]:
        raw_model = model.removeprefix("ollama:")
        body: dict[str, Any] = {
            "model": raw_model,
            "messages": [
                {"role": m.get("role", "user"), "content": _content_text(m.get("content"))}
                for m in messages
            ],
            "stream": True,
        }
        opts = {k: options[k] for k in ("temperature", "top_p", "seed") if k in options}
        if opts:
            body["options"] = opts

        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            async with client.stream("POST", f"{self._base_url()}/api/chat", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = item.get("message", {}).get("content", "")
                    if content:
                        yield str(content)

    async def health_check(self) -> dict[str, Any]:
        if not get_settings().ollama_enabled:
            return {"enabled": False}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url()}/api/tags")
            return {"enabled": True, "reachable": resp.status_code < 500, "status_code": resp.status_code}
        except httpx.HTTPError as exc:
            return {"enabled": True, "reachable": False, "error": type(exc).__name__}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)
