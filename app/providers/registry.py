from __future__ import annotations

from typing import Any

from app.providers.base import BaseProvider


class ProviderRegistry:
    """Central registry that maps provider names to their implementations.

    A provider is registered once at startup. The registry is also the place
    where the fallback chain lives: when a request comes in without an explicit
    provider, the registry tries each provider in priority order until one
    succeeds.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        # Ordered list of provider names for fallback (highest priority first).
        self._priority: list[str] = []

    def register(self, provider: BaseProvider, priority: int = 100) -> None:
        """Register a provider.

        Lower priority number = tried first in the fallback chain.
        If two providers share the same priority, the one registered first wins.
        """
        name = provider.name.strip().lower()
        if not name:
            raise ValueError("Provider name cannot be empty")
        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")
        self._providers[name] = provider
        # Insert by priority (stable sort).
        self._priority.append((priority, name))
        self._priority.sort(key=lambda t: t[0])

    def get(self, name: str) -> BaseProvider:
        key = name.strip().lower()
        if key not in self._providers:
            raise LookupError(f"Unknown provider: {name}")
        return self._providers[key]

    def names(self) -> list[str]:
        return sorted(self._providers)

    def priority_order(self) -> list[str]:
        """Provider names ordered by priority (best first)."""
        return [name for _, name in self._priority]

    async def list_all_models(self) -> list[dict[str, Any]]:
        """Aggregate models from every registered provider."""
        models: list[dict[str, Any]] = []
        for name in self.names():
            try:
                models.extend(await self._providers[name].list_models())
            except Exception:
                pass
        return models

    def resolve_provider(self, model_id: str) -> BaseProvider | None:
        """Find which provider owns a given model_id."""
        # Prefix-based routing: "ollama:*" → ollama, "gptbridge-*" → gptbridge, etc.
        for name, provider in self._providers.items():
            if model_id.startswith(f"{name}:") or model_id == name:
                return provider
        return None
