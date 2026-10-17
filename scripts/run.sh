#!/usr/bin/env bash
# Starts the gateway, binding to 127.0.0.1 by default (see README for why
# that's the safe default when GTG_API_KEY is empty).
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${APP_HOST:-127.0.0.1}"
PORT="${APP_PORT:-8080}"

exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
