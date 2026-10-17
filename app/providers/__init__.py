"""Provider registry singleton and startup initialization."""
from __future__ import annotations

from app.providers.registry import ProviderRegistry

# The single registry instance used throughout the application.
registry = ProviderRegistry()


def init_providers() -> None:
    """Register all configured providers.  Called once at application startup."""
    from app.core.config import get_settings
    settings = get_settings()

    # g4f in-process provider (priority 10 — tried first for free models).
    if settings.g4f_enabled:
        from app.providers.g4f_provider import G4FProvider
        registry.register(G4FProvider(), priority=10)

    # Ollama local models (priority 20).
    if settings.ollama_enabled:
        from app.providers.ollama import OllamaProvider
        registry.register(OllamaProvider(), priority=20)

    # Perchance / URV AI Chat (priority 15 — opt-in, browser bridge).
    if getattr(settings, "perchance_enabled", False):
        from app.providers.perchance import PerchanceProvider
        registry.register(PerchanceProvider(), priority=15)

    # Legacy GPTBridge sidecar (priority 30 — only if explicitly enabled).
    if settings.gptbridge_enabled:
        from app.providers.gptbridge import GptBridgeProvider
        registry.register(GptBridgeProvider(), priority=30)

    # Onyx / FreeTheAI (HTTP, no browser).
    from app.providers.onyx import OnyxProvider
    registry.register(OnyxProvider(
        base_url=settings.onyx_base_url,
        api_key=settings.onyx_api_key,
        timeout=settings.onyx_timeout,
    ), priority=20)
