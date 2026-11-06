#!/usr/bin/env bash
# Start v kontejneru: backend (API + worker + plánovač) na 127.0.0.1:8000, frontend na $PORT.
set -euo pipefail

if [ -z "${APP_PASSWORD:-}" ] && [ "${ALLOW_NO_PASSWORD:-0}" != "1" ]; then
  echo "✖ Chybí APP_PASSWORD. Aplikace na veřejné adrese musí mít heslo – nastavte proměnnou/secret APP_PASSWORD."
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "⚠ DATABASE_URL není nastaveno – používám SQLite v kontejneru. Na hostingu bez trvalého disku se data po restartu ztratí."
fi
mkdir -p "${DATA_DIR:-/app/data}"

cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND=$!

# počkej na backend (migrace DB proběhnou při startu)
for i in $(seq 1 60); do
  if python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" 2>/dev/null; then break; fi
  if ! kill -0 "$BACKEND" 2>/dev/null; then echo "✖ Backend se nespustil"; exit 1; fi
  sleep 1
done

cd /app/frontend
LEADHUNTER_API_URL=http://127.0.0.1:8000 node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "${PORT:-7860}" &
FRONTEND=$!
echo "✓ Lead Hunter běží na portu ${PORT:-7860}"

wait -n "$BACKEND" "$FRONTEND"
EXIT=$?
kill "$BACKEND" "$FRONTEND" 2>/dev/null || true
exit $EXIT
