#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dev}"

case "$MODE" in
  dev)
    # Hot reload for local development, but ignore virtualenv and storage changes.
    python -m uvicorn backend.app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --reload \
      --reload-exclude '.venv/*' \
      --reload-exclude 'storage/*' \
      --reload-exclude '__pycache__/*'
    ;;
  web)
    # Production-like web process: no reload, no in-process OCR worker.
    ENABLE_IN_PROCESS_WORKER=false \
    python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    # Dedicated OCR worker process that polls queued jobs from DB.
    python -m backend.app.worker
    ;;
  prod)
    # Convenience mode: starts web + worker in the same shell for local testing.
    trap 'kill 0' EXIT
    ENABLE_IN_PROCESS_WORKER=false python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
    python -m backend.app.worker
    ;;
  *)
    echo "Usage: $0 [dev|web|worker|prod]"
    exit 1
    ;;
esac
