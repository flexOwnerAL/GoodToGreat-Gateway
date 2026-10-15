# GoodToGreat-Gateway

An asynchronous API gateway with an in-process DeepBridge integration.

**Author:** @flexOwnerAL

## Features

- Health endpoint: `GET /health`
- OpenAI-compatible model listing: `GET /v1/models`
- Chat completions: `POST /v1/chat/completions`
- Streaming support through Server-Sent Events
- DeepBridge integration without a separate DeepBridge server
- Local session storage excluded from Git

## Development

Create and activate a virtual environment, then install the project:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Start the gateway:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Health check: http://127.0.0.1:8080/health

API documentation: http://127.0.0.1:8080/docs

## DeepBridge authentication

DeepBridge uses an unofficial integration with the DeepSeek web client.
Its availability depends on DeepSeek's service, account access, and
web-client protocol; it is not the official DeepSeek API.

Authenticate using the project's supported login flow:

```bash
python -m app.integrations.deepbridge.webauth
```

Keep session files, cookies, tokens, and credentials private. Local
DeepBridge data is stored under `.data/deepbridge/` and must not be committed.

## Licensing

See the upstream license notice included with DeepBridge. Check the
gateway's own licensing requirements before redistributing the combined
project.
