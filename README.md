# GoodToGreat-Gateway (GTG)

Async OpenAI-compatible AI gateway with DeepBridge, an in-process **g4f** provider, and local **Ollama** support — no cloud API keys needed.

**Author:** @flexOwnerAL · Version: 0.5.0

---

## What's included

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /health/providers` | Reachability per provider (DeepBridge never probed) |
| `GET /metrics` | Aggregate request counts, errors, uptime, latency |
| `GET /v1/models` | All available models across all providers |
| `GET /v1/models/{id}` | Single model lookup |
| `POST /v1/chat/completions` | OpenAI-compatible completions + SSE streaming |

**Features:**
- Optional bearer-token auth (`GTG_API_KEY`) for `/v1/*`
- Token-bucket rate limiting: 30 req/60s per key or IP, configurable
- Request body size cap and security response headers
- OpenAI-compatible error envelope on all endpoints
- Automatic **fallback chain**: if the requested model is unknown, GTG tries providers in priority order (g4f → Ollama → legacy GPTBridge)

---

## Providers

### DeepBridge (`deepseek-chat`, `deepseek-expert`)
Unofficial integration with the DeepSeek web client (cookies + PoW). Unchanged from the original GTG archive. Authenticate once:
```bash
python -m app.integrations.deepbridge.webauth
```

### g4f — in-process free provider (`g4f:*`)
[g4f](https://github.com/xtekky/gpt4free) runs **inside the GTG process** — no separate server, no sidecar.  
Available model IDs: `g4f:auto`, `g4f:gpt-4o`, `g4f:gpt-4o-mini`, `g4f:gpt-4`, `g4f:claude-3-5-sonnet`, `g4f:gemini-pro`, `g4f:llama-3.1-70b`, `g4f:mixtral-8x7b`.

Use `g4f:auto` to let g4f pick the best available upstream provider automatically.

Set `G4F_PROVIDER` in `.env` to force a specific g4f provider class (e.g. `DDG`, `Airforce`, `Blackbox`).

> **Note:** g4f relies on third-party websites. Availability varies. "Free" means no API key, not guaranteed uptime.

### Ollama — local models (`ollama:<model>`)
Install Ollama, pull a model, and GTG discovers it automatically:
```bash
ollama pull qwen2.5:3b
```
Set `OLLAMA_ENABLED=true` (default). No cloud API key needed.

### Legacy GPTBridge (`gptbridge-free`)
Kept for backward compatibility with existing setups running a separate Free-GPT4-WEB-API process. **Disabled by default.** For new deployments, use the built-in g4f provider instead.

---

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Quick example

```bash
# g4f (no config needed)
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"g4f:auto","messages":[{"role":"user","content":"Hello"}]}'

# Ollama (requires local Ollama + model)
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"ollama:qwen2.5:3b","messages":[{"role":"user","content":"Hello"}]}'

# With API key
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Authorization: Bearer YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"model":"g4f:auto","messages":[{"role":"user","content":"Hello"}]}'
```

## Authentication (optional)

Generate an API key and set it in `.env`:
```bash
python scripts/gen_api_key.py
```

## Rate limiting

`/v1/*` is protected by a token-bucket limiter — 30 requests per 60 seconds per API key (or IP). Configurable via `RATE_LIMIT_*` in `.env`. See [`docs/RATE_LIMITING.md`](docs/RATE_LIMITING.md).

> **Note:** Rate-limit state is in-process memory. Multiple workers each enforce their own limit independently. Use a single worker, or move state to Redis for multi-process deployments.

## Fallback routing

When you request model `g4f:auto` (or any unknown model ID), GTG tries providers in priority order:
1. **g4f** (priority 10) — in-process, works out of the box
2. **Ollama** (priority 20) — if a local model is running
3. **GPTBridge** (priority 30) — only if explicitly enabled

The first provider that responds successfully wins. On total failure, GTG returns a 503 with details.

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

Covers: health/metrics, model listing, g4f and Ollama completions, API-key gate, rate limiting (HTTP + unit), OpenAI error envelope, provider registry, `/health/providers`.

CI (`.github/workflows/ci.yml`) runs `ruff` and `pytest` on Python 3.10–3.12.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Example configs in `config/` (docker-compose, nginx, systemd). Helper scripts in `scripts/`.

## Licensing

The DeepBridge integration includes its upstream license notice. g4f is subject to its own license. Free-GPT4-WEB-API is GPL-3.0; GTG no longer includes its source (the g4f package replaces it). Ollama model weights and provider terms are separate.
