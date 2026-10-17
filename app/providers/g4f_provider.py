"""g4f (GPT4Free) in-process provider.

Replaces the external Free-GPT4-WEB-API sidecar. Instead of running a
separate Flask server and proxying to it via HTTP, we import g4f directly
and call it in-process. This gives:
  - No separate process to manage / port to configure.
  - Real async streaming (g4f supports AsyncClient).
  - Full model/provider selection without a sidecar config file.

Model IDs exposed by this provider are prefixed with "g4f:" so they don't
collide with DeepBridge or Ollama models.
  e.g.  g4f:gpt-4o,  g4f:gpt-4,  g4f:claude-3-5-sonnet

The model after the "g4f:" prefix is passed directly to g4f — any model
string that g4f supports is valid. Use "g4f:auto" to let g4f pick the best
available provider automatically (default).

Provider selection:
  Set G4F_PROVIDER in .env to force a specific g4f provider class name,
  e.g. "Airforce", "DDG", "Blackbox", etc. Leave empty for auto-selection.

Limitations:
  - g4f relies on third-party websites. Availability fluctuates.
  - Not all g4f providers support streaming; for those, text is buffered.
  - Rate limits are imposed by upstream websites, not by GTG.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.providers.base import BaseProvider
from app.utils.tokens import usage_block

logger = logging.getLogger("goodtogreat.g4f")

# Lazy import — g4f is a large dependency; only load when the provider is used.
_g4f_imported = False
_g4f_error: Exception | None = None


def _import_g4f():
    global _g4f_imported, _g4f_error
    if _g4f_imported:
        return
    try:
        import g4f  # noqa: F401
        _g4f_imported = True
    except ImportError as exc:
        _g4f_error = exc
        raise RuntimeError(
            "g4f is not installed. Install it with: pip install g4f"
        ) from exc


# Well-known g4f model aliases that GTG exposes by default.
_DEFAULT_MODELS = [
    "g4f:auto",
    "g4f:gpt-4o",
    "g4f:gpt-4o-mini",
    "g4f:gpt-4",
    "g4f:claude-3-5-sonnet",
    "g4f:gemini-pro",
    "g4f:llama-3.1-70b",
    "g4f:mixtral-8x7b",
]


class G4FProvider(BaseProvider):
    name = "g4f"

    def _settings(self):
        return get_settings()

    async def list_models(self) -> list[dict[str, Any]]:
        if not self._settings().g4f_enabled:
            return []
        now = int(time.time())
        return [
            {"id": mid, "object": "model", "created": now, "owned_by": "g4f"}
            for mid in _DEFAULT_MODELS
        ]

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        _import_g4f()
        import g4f
        from g4f.client import AsyncClient

        raw_model = model.removeprefix("g4f:") or "auto"
        if raw_model == "auto":
            raw_model = g4f.models.default

        provider_name = self._settings().g4f_provider or None
        provider_cls = None
        if provider_name:
            provider_cls = _resolve_provider(provider_name)

        normalized = _normalize_messages(messages)
        client = AsyncClient()

        try:
            response = await client.chat.completions.create(
                model=raw_model,
                messages=normalized,
                provider=provider_cls,
                stream=False,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("g4f generate failed: %s", exc)
            raise

        prompt_str = " ".join(m.get("content", "") or "" for m in normalized)
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage_block(prompt_str, content),
        }

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> AsyncIterator[str]:
        _import_g4f()
        import g4f
        from g4f.client import AsyncClient

        raw_model = model.removeprefix("g4f:") or "auto"
        if raw_model == "auto":
            raw_model = g4f.models.default

        provider_name = self._settings().g4f_provider or None
        provider_cls = None
        if provider_name:
            provider_cls = _resolve_provider(provider_name)

        normalized = _normalize_messages(messages)
        client = AsyncClient()

        try:
            response = await client.chat.completions.create(
                model=raw_model,
                messages=normalized,
                provider=provider_cls,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            logger.warning("g4f stream failed: %s", exc)
            raise

    async def health_check(self) -> dict[str, Any]:
        settings = self._settings()
        if not settings.g4f_enabled:
            return {"enabled": False}
        if _g4f_error:
            return {"enabled": True, "reachable": False, "error": str(_g4f_error)}
        try:
            _import_g4f()
            return {"enabled": True, "reachable": True, "note": "g4f in-process, no network probe"}
        except RuntimeError as exc:
            return {"enabled": True, "reachable": False, "error": str(exc)}


def _resolve_provider(name: str):
    """Resolve a g4f provider class by name."""
    try:
        import g4f.Provider as providers
        return getattr(providers, name)
    except AttributeError:
        logger.warning("Unknown g4f provider '%s', using auto", name)
        return None


def _normalize_messages(messages: list[dict]) -> list[dict[str, str]]:
    """Convert OpenAI messages to plain strings for g4f."""
    result = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        result.append({"role": str(role), "content": str(content)})
    return result
