from app.providers.base import BaseProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        name = provider.name.strip().lower()
        if not name:
            raise ValueError("Provider name cannot be empty")
        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> BaseProvider:
        key = name.strip().lower()
        if key not in self._providers:
            raise LookupError(f"Unknown provider: {name}")
        return self._providers[key]

    def names(self) -> list[str]:
        return sorted(self._providers)
