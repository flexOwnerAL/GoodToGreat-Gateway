# Changelog

## 0.5.0 (2026-10-16)

### Breaking changes
- `GPTBRIDGE_ENABLED` now defaults to `false`. Use the built-in g4f provider instead.
- `app/providers/remote_free.py` removed — logic moved into `OllamaProvider` and `GptBridgeProvider` classes.

### New
- **g4f in-process provider** (`g4f:*` model IDs). Replaces the external Free-GPT4-WEB-API sidecar. g4f runs inside GTG — no separate process, no port to configure. Supports auto model selection and forced provider via `G4F_PROVIDER`.
- **ProviderRegistry** is now wired up. `BaseProvider`/`ProviderRegistry` are no longer stubs — `OllamaProvider`, `G4FProvider`, and `GptBridgeProvider` are all registered at startup.
- **Fallback routing**: unknown model IDs trigger an automatic fallback chain (g4f → Ollama → GPTBridge by priority).
- `BaseProvider.stream()` default implementation (yield full generate response); subclasses override for true streaming.
- `BaseProvider.health_check()` — per-provider reachability, surfaced in `/health/providers`.
- `ProviderRegistry.priority_order()` — ordered list for fallback.
- `ProviderRegistry.list_all_models()` — aggregate model listing.
- `ProviderRegistry.resolve_provider()` — prefix-based model-to-provider routing.
- Healthcheck in Dockerfile and docker-compose.
- Non-root user in Docker image.
- `pytest-asyncio` added to dev dependencies; `asyncio_mode = "auto"` in pytest config.

### Fixed
- Garbage directory `{docs,scripts,config,.github/workflows}/` (shell glob artifact) removed.
- `GPTBRIDGE_ENABLED=true` no longer silently fails on fresh installs — g4f is the default now.
- `docs/ARCHITECTURE.md` updated to match actual implementation.
- `test_oversized_body_is_rejected_before_parsing` — uses middleware-level settings patch correctly.

### Unchanged
- DeepBridge integration (`deepseek-chat`, `deepseek-expert`) — not touched.
- Rate limiting, auth middleware, observability, token estimation.
- All existing DeepBridge-specific options (`thinking`, `search`, `conversation_id`).

## 0.4.0

Initial public release with DeepBridge, stub GPTBridge sidecar adapter, and Ollama support.
