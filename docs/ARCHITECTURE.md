# Architecture

## Overview

GoodToGreat-Gateway (GTG) is an async FastAPI application. All AI traffic enters through one endpoint (`POST /v1/chat/completions`) and is dispatched to one of several providers.

```
┌─────────────────────────────────────────────────────┐
│  FastAPI (app/main.py)                               │
│                                                      │
│  Middleware chain (per request):                     │
│    1. Body size cap (413 before JSON parse)          │
│    2. Bearer-token auth (401 if GTG_API_KEY is set)  │
│    3. Token-bucket rate limit (429 + Retry-After)    │
│    4. Metrics recording                              │
│    5. Security headers                               │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │  /v1/chat/completions  │
         └───────────┬───────────┘
                     │
          ┌──────────▼──────────┐
          │  Model dispatch      │
          │  (app/api/routes/)   │
          └──────────┬──────────┘
         ┌───────────┼───────────┐
         ▼           ▼           ▼
  DeepBridge    ProviderRegistry  Fallback chain
  (direct)      .resolve_provider  (priority order)
         │           │
    DeepSeek    ┌────┴────────────────┐
    web client  │  g4f (priority 10)  │
                │  Ollama (priority 20)│
                │  GPTBridge (30, opt) │
                └─────────────────────┘
```

## Provider system

All non-DeepBridge providers implement `BaseProvider` (`app/providers/base.py`):

```python
class BaseProvider(ABC):
    name: str
    async def list_models(self) -> list[dict]: ...
    async def generate(self, model, messages, **options) -> dict: ...
    async def stream(self, model, messages, **options) -> AsyncIterator[str]: ...
    async def health_check(self) -> dict: ...
```

Providers are registered at startup in `app/providers/__init__.py` and stored in a `ProviderRegistry` singleton. The registry handles:
- **Model listing** (`list_all_models()`) — aggregated from all providers
- **Provider resolution** (`resolve_provider(model_id)`) — prefix-based routing
- **Priority ordering** (`priority_order()`) — for fallback

## Fallback routing

When a request arrives with an unknown model ID (e.g. `g4f:auto` with no matching provider prefix, or literally `auto`), GTG tries each provider in priority order and returns the first successful response.

## DeepBridge

DeepBridge uses an unofficial integration with the DeepSeek web client and is not implemented as a `BaseProvider` subclass — it predates the provider system and is kept unchanged. It is routed directly in the request handler before the registry is consulted.

## Rate limiting

Token-bucket implementation in `app/core/ratelimit.py`. State is process-local (in-memory dict). For multi-worker deployments, move state to a shared store such as Redis.

## Observability

`GET /metrics` returns aggregate counters (requests, errors, latency per route). No prompts or credentials are ever included.
