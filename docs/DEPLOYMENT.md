# Deployment

## Quick local run
```bash
./scripts/setup_dev.sh
./scripts/run.sh
```

## Docker
```bash
docker compose -f config/docker-compose.yml up -d --build
```
Builds the gateway image from the root `Dockerfile` and starts an Ollama
sidecar. GPTBridge/DeepBridge aren't included in the compose file — see
below and `docs/ARCHITECTURE.md`.

## systemd
Copy `config/gtg-gateway.service.example` to
`/etc/systemd/system/gtg-gateway.service`, adjust the paths and user, then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gtg-gateway
```

## Reverse proxy / TLS
See `config/nginx.conf.example`. Important: `proxy_buffering off;` is
required or SSE streaming responses (`stream: true`) will arrive as one
buffered chunk instead of incrementally.

## Embedding GPTBridge (Free-GPT4-WEB-API) in-process

Right now `GPTBridge` is an HTTP adapter to a **separately run** instance of
the upstream Free-GPT4-WEB-API project (GPL-3.0). That's a deliberate
boundary, not a missing feature: merging its source into this repo means you
take on GPL-3.0's source-distribution obligations for the combined work, so
it should be a decision you make with the license in front of you, not
something done silently on your behalf. To do it:

1. Pull the upstream source yourself (this environment has no network
   access, so it couldn't be fetched automatically here).
2. Vendor it under e.g. `app/integrations/gptbridge/vendor/`, keeping its
   `LICENSE` file and any `NOTICE`/attribution files intact — mirror how
   `app/integrations/deepbridge/UPSTREAM_LICENSE.txt` is kept alongside that
   integration.
3. Replace the HTTP call in `app/providers/remote_free.py::gptbridge_chat`
   with a direct in-process call into the vendored module, instead of
   `httpx` hitting `GPTBRIDGE_BASE_URL`.
4. If you distribute your modified gateway to others, GPL-3.0 requires you
   make the combined source available under GPL-3.0 too — update this
   project's `LICENSE`/README to reflect that for the combined work.

Until then, running the upstream project as its own process
(`GPTBRIDGE_BASE_URL=http://127.0.0.1:5500`) keeps the two codebases and
licenses cleanly separated, which is why the current adapter works that way.

## DeepBridge in a container
DeepBridge's one-time login uses Playwright (a real/headless browser) to pass
the DeepSeek site's human-verification check. That doesn't fit a minimal
headless container well. Two options:
- Run `python -m app.integrations.deepbridge.webauth` on the host (or a
  machine with a display) once, then mount the resulting session/profile
  directory into the container as a volume.
- Skip DeepBridge in containerized deployments and serve `gptbridge-free` /
  `ollama:*` models only (set `GPTBRIDGE_ENABLED` / `OLLAMA_ENABLED`
  accordingly; DeepBridge's models stay listed but will return a 503
  `authentication_error` until a session exists).
