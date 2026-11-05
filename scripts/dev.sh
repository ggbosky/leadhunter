#!/usr/bin/env bash
# Vývojový režim s automatickým reloadem
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' EXIT
(cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
(cd frontend && npx next dev -p 3000) &
wait
