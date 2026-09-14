#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create the local environment first: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt' >&2
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  echo 'Build the interface first: cd frontend && npm ci && npm run build' >&2
  exit 1
fi
if [[ -f .env ]]; then
  exec .venv/bin/python -m uvicorn requirement_reuse_service.main:app --app-dir requirement-reuse-service --host 127.0.0.1 --port 8011 --env-file .env
fi
exec .venv/bin/python -m uvicorn requirement_reuse_service.main:app --app-dir requirement-reuse-service --host 127.0.0.1 --port 8011
