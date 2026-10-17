"""OnyxProvider — HTTP-шлюз к FreeTheAI (OpenAI-совместимый).

Без браузера, чистый httpx. Транспорт — обычный POST /v1/chat/completions.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import BaseProvider
from . import onyx_models


class OnyxProvider(BaseProvider):
    name = "onyx"

    def __init__(self, base_url: str, api_key: str = "", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = int(timeout) if timeout else 120

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def list_models(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    payload = r.json()
                    if isinstance(payload, dict):
                        data = list(payload.get("data") or [])
        except Exception:
            data = []
        # Алиасы всегда сверху, чтобы были видны в UI даже если upstream молчит.
        alias_items = [
            {"id": a, "object": "model", "owned_by": "onyx"}
            for a in onyx_models.aliases()
        ]
        seen = {m["id"] for m in data}
        data = alias_items + [m for m in data if m.get("id") not in seen]
        return data

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        real_model = onyx_models.resolve(model)
        payload: dict[str, Any] = {
            "model": real_model,
            "messages": messages,
            "stream": False,
        }
        payload.update(options)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            # upstream может отдать 4xx/5xx с текстом — пробрасываем как OpenAIStyle
            if r.status_code >= 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = {"error": r.text[:500]}
                raise RuntimeError(f"onyx upstream HTTP {r.status_code}: {detail}")
            return r.json()
