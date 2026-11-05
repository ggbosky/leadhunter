#!/usr/bin/env bash
# Jednorázová instalace v GitHub Codespaces
set -euo pipefail
./scripts/setup.sh
# systémové knihovny pro Chromium (screenshoty)
sudo backend/.venv/bin/python -m playwright install-deps chromium || true
echo "✓ Lead Hunter připraven – otevřete port 3000 (záložka PORTS)."
