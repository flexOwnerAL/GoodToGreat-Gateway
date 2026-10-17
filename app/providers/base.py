from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """Return models this provider exposes in OpenAI /v1/models format."""
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns OpenAI-shaped response body."""
        raise NotImplementedError

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> AsyncIterator[str]:
        """Streaming chat — yields text chunks.
        Default: call generate() and yield the whole response as one chunk.
        Override for true token-by-token streaming.
        """
        result = await self.generate(model, messages, **options)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        yield content

    async def health_check(self) -> dict[str, Any]:
        """Return provider reachability info for /health/providers.
        Override in subclasses that can do a lightweight probe.
        """
        return {"reachable": True, "note": "no probe implemented"}
