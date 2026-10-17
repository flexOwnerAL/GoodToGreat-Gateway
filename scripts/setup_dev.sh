#!/usr/bin/env bash
# Sets up a local dev environment: venv, deps, .env.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it before running in production."
fi

echo "Done. Activate with: . .venv/bin/activate"
echo "Run tests with: pytest -q"
echo "Start the server with: ./scripts/run.sh"
