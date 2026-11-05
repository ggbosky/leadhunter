#!/usr/bin/env bash
# Instalace závislostí backendu a frontendu (Linux / macOS)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ Backend (Python)"
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
# Chromium pro screenshoty (pokud ho Playwright ještě nemá)
python -m playwright install chromium || echo "⚠ Playwright Chromium se nepodařilo stáhnout – nastavte PLAYWRIGHT_EXECUTABLE_PATH v backend/.env"
[ -f .env ] || cp .env.example .env
python -m app.cli migrate
cd ..

echo "→ Frontend (Node.js)"
cd frontend
npm install
[ -f .env.local ] || cp .env.example .env.local
npm run build
cd ..
echo "✓ Hotovo. Spusťte: ./scripts/start.sh"
