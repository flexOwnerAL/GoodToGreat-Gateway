"""Provider health service.

Kept for backward compatibility. The main health logic now lives in each
provider's health_check() method. This module is no longer called directly
from routes — /health/providers in main.py queries the registry directly.
"""
from __future__ import annotations

# Re-export for any code that may import from here.
from app.providers import registry


async def provider_statuses() -> dict:
    """Aggregate health status from all registered providers + DeepBridge."""
    result = {
        "deepbridge": {
            "enabled": True,
            "note": "Not probed — avoids triggering the DeepSeek login/PoW flow.",
        }
    }
    for name in registry.names():
        try:
            provider = registry.get(name)
            result[name] = await provider.health_check()
        except Exception as exc:
            result[name] = {"reachable": False, "error": str(exc)}
    return result
