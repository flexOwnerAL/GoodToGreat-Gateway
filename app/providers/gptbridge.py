"""Legacy GPTBridge provider — external Free-GPT4-WEB-API sidecar.

This provider is kept for backward compatibility with setups that already
run a separate Free-GPT4-WEB-API process.  For new deployments, prefer the
built-in g4f provider (G4FProvider), which runs in-process and needs no
separate server.

Enable with: GPTBRIDGE_ENABLED=true in .env
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider
from app.utils.tokens import usage_block


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


def _prompt_from_messages(messages: list[dict]) -> str:
    lines: list[str] = []
    for m in messages:
        role = str(m.get("role", "user")).strip().capitalize()
        lines.append(f"{role}: {_content_text(m.get('content'))}")
    if messages and messages[-1].get("role") == "user":
        lines.append("Assistant:")
    return "\n\n".join(lines)


class GptBridgeProvider(BaseProvider):
    name = "gptbridge"

    def _settings(self):
        return get_settings()

    async def list_models(self) -> list[dict[str, Any]]:
        if not self._settings().gptbridge_enabled:
            return []
        now = int(time.time())
        return [
            {"id": "gptbridge-free", "object": "model", "created": now, "owned_by": "gptbridge"}
        ]

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        settings = self._settings()
        prompt = _prompt_from_messages(messages)
        async with httpx.AsyncClient(timeout=settings.gptbridge_timeout_seconds) as client:
            response = await client.get(
                settings.gptbridge_base_url.rstrip("/") + "/",
                params={"text": prompt},
            )
            response.raise_for_status()
            content = response.text.strip()

        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage_block(prompt, content),
        }

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> AsyncIterator[str]:
        """GPTBridge upstream returns a complete response; chunk it for streaming."""
        result = await self.generate(model, messages, **options)
        content = result["choices"][0]["message"]["content"]
        chunk_size = 48
        for offset in range(0, len(content), chunk_size):
            yield content[offset:offset + chunk_size]

    async def health_check(self) -> dict[str, Any]:
        settings = self._settings()
        if not settings.gptbridge_enabled:
            return {"enabled": False}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(settings.gptbridge_base_url.rstrip("/") + "/")
            return {"enabled": True, "reachable": resp.status_code < 500, "status_code": resp.status_code}
        except httpx.HTTPError as exc:
            return {"enabled": True, "reachable": False, "error": type(exc).__name__}
