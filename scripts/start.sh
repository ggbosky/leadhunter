#!/usr/bin/env bash
# Spustí backend (API + worker + plánovač) a frontend. Ukončení: Ctrl+C
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' EXIT

(cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000) &
(cd frontend && npx next start -p 3000) &
echo "Lead Hunter: http://localhost:3000  (API: http://127.0.0.1:8000/docs)"
wait
