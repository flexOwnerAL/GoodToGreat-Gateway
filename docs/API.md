# API Reference

Base URL: `http://127.0.0.1:8080` (default)

All `/v1/*` endpoints accept and return JSON. When `GTG_API_KEY` is set, include `Authorization: Bearer <key>` on every `/v1/*` request.

---

## GET /health

Liveness check — always returns 200 while the process is running.

```json
{"status": "ok", "service": "gateway", "version": "0.5.0"}
```

## GET /health/providers

Best-effort reachability per provider. DeepBridge is never probed (avoids triggering its login/PoW flow).

```json
{
  "deepbridge": {"enabled": true, "note": "Not probed ..."},
  "g4f": {"enabled": true, "reachable": true, "note": "g4f in-process, no network probe"},
  "ollama": {"enabled": true, "reachable": true, "status_code": 200}
}
```

## GET /metrics

Aggregate counters. No prompts or credentials included.

## GET /v1/models

List all available models across all providers.

## GET /v1/models/{id}

Single model lookup. Returns 404 with OpenAI error shape if not found.

## POST /v1/chat/completions

OpenAI-compatible chat completion.

**Request:**
```json
{
  "model": "g4f:auto",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "temperature": 0.7
}
```

**Response:**
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "g4f:auto",
  "system_fingerprint": "fp_gtg_gateway",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
}
```

> **Token counts** are estimates (~4 chars per token). No provider currently returns exact counts.

**DeepBridge-only fields:**
- `thinking` (bool) — enable chain-of-thought
- `search` (bool) — enable web search
- `conversation_id` (string) — resume an existing conversation

**Model IDs:**
| ID | Provider |
|---|---|
| `deepseek-chat` | DeepBridge |
| `deepseek-expert` | DeepBridge |
| `g4f:auto` | g4f (auto-select) |
| `g4f:gpt-4o`, `g4f:gpt-4`, … | g4f (specific model) |
| `ollama:<model>` | Ollama local |
| `gptbridge-free` | Legacy GPTBridge sidecar |

**Streaming:** set `"stream": true` to receive SSE chunks (`text/event-stream`). Each chunk is `data: {...}\n\n`. The stream ends with `data: [DONE]\n\n`.
