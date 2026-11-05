#!/usr/bin/env python3
"""Spouštěč Project Two Lead Hunter – Windows / macOS / Linux.

Použití (v adresáři projektu):
    python run.py          (Windows: py run.py)

Při prvním spuštění vše nainstaluje (Python balíčky, Chromium pro screenshoty,
Node balíčky, build frontendu), pak spustí backend i frontend a otevře
aplikaci v prohlížeči. Ukončení: Ctrl+C.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
WIN = os.name == "nt"
APP_PORT = int(os.environ.get("LEADHUNTER_PORT", "3000"))
API_PORT = int(os.environ.get("LEADHUNTER_API_PORT", "8000"))


def say(msg: str) -> None:
    print(f"\n▶ {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n✖ {msg}", flush=True)
    if WIN:
        input("Stiskněte Enter pro ukončení…")
    sys.exit(1)


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    res = subprocess.run(cmd, cwd=cwd, env=env)
    if res.returncode != 0:
        fail(f"Příkaz selhal: {' '.join(cmd)}")


def digest(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def stamp_ok(stamp: Path, value: str) -> bool:
    return stamp.exists() and stamp.read_text() == value


def check_tools() -> str:
    if sys.version_info < (3, 11):
        fail(f"Je potřeba Python 3.11 nebo novější (máte {sys.version.split()[0]}). Stáhněte z https://www.python.org/downloads/")
    npm = shutil.which("npm.cmd" if WIN else "npm") or shutil.which("npm")
    node = shutil.which("node")
    if not node or not npm:
        fail("Chybí Node.js (verze 20+). Stáhněte z https://nodejs.org/ a spusťte znovu.")
    ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if int(ver.split(".")[0]) < 20:
        fail(f"Je potřeba Node.js 20 nebo novější (máte {ver}).")
    return npm


def setup_backend() -> Path:
    venv = BACKEND / ".venv"
    py = venv / ("Scripts/python.exe" if WIN else "bin/python")
    if not py.exists():
        say("Vytvářím Python prostředí…")
        run([sys.executable, "-m", "venv", str(venv)], BACKEND)
    req = digest(BACKEND / "requirements.txt")
    stamp = venv / ".installed"
    if not stamp_ok(stamp, req):
        say("Instaluji Python balíčky (jen poprvé, pár minut)…")
        run([str(py), "-m", "pip", "install", "--upgrade", "pip", "-q"], BACKEND)
        run([str(py), "-m", "pip", "install", "-r", "requirements.txt", "-q"], BACKEND)
        stamp.write_text(req)
    pw_stamp = venv / ".chromium"
    if not pw_stamp.exists():
        say("Stahuji Chromium pro screenshoty webů…")
        res = subprocess.run([str(py), "-m", "playwright", "install", "chromium"], cwd=BACKEND)
        if res.returncode == 0:
            pw_stamp.write_text("ok")
        else:
            print("⚠ Chromium se nepodařilo stáhnout – aplikace poběží, ale bez screenshotů.")
    env_file = BACKEND / ".env"
    if not env_file.exists():
        shutil.copy(BACKEND / ".env.example", env_file)
    return py


def setup_frontend(npm: str) -> None:
    lock = digest(FRONTEND / "package-lock.json", FRONTEND / "package.json")
    stamp = FRONTEND / "node_modules" / ".installed"
    if not stamp_ok(stamp, lock):
        say("Instaluji balíčky frontendu (jen poprvé)…")
        run([npm, "install", "--no-audit", "--no-fund"], FRONTEND)
        stamp.write_text(lock)
    env_local = FRONTEND / ".env.local"
    if not env_local.exists():
        shutil.copy(FRONTEND / ".env.example", env_local)
    build_id = FRONTEND / ".next" / "BUILD_ID"
    sources = [p for d in ("app", "components", "lib") for p in (FRONTEND / d).rglob("*") if p.is_file()]
    sources += [FRONTEND / f for f in ("package.json", "next.config.ts", "tsconfig.json")]
    newest = max(p.stat().st_mtime for p in sources if p.exists())
    if not build_id.exists() or build_id.stat().st_mtime < newest:
        say("Sestavuji frontend…")
        env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
        run([npm, "run", "build"], FRONTEND, env=env)


def wait_for(url: str, timeout: float = 90) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return False


def main() -> None:
    print("Project Two Lead Hunter")
    npm = check_tools()
    py = setup_backend()
    setup_frontend(npm)

    say("Spouštím aplikaci…")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0
    backend = subprocess.Popen([str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
                               cwd=BACKEND, creationflags=flags)
    if not wait_for(f"http://127.0.0.1:{API_PORT}/api/health"):
        backend.terminate()
        fail("Backend se nespustil – podívejte se na výpis výše.")
    next_bin = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
    env = {**os.environ, "LEADHUNTER_API_URL": f"http://127.0.0.1:{API_PORT}", "NEXT_TELEMETRY_DISABLED": "1"}
    frontend = subprocess.Popen([shutil.which("node") or "node", str(next_bin), "start", "-p", str(APP_PORT)],
                                cwd=FRONTEND, env=env, creationflags=flags)
    url = f"http://localhost:{APP_PORT}"
    if not wait_for(url):
        frontend.terminate()
        backend.terminate()
        fail("Frontend se nespustil – podívejte se na výpis výše.")
    print(f"\n✓ Lead Hunter běží: {url}\n  (automatizace běží, dokud je toto okno otevřené; ukončení Ctrl+C)\n", flush=True)
    if os.environ.get("LEADHUNTER_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (frontend, backend):
            if p.poll() is None:
                p.terminate()
        for p in (frontend, backend):
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Ukončeno.")


if __name__ == "__main__":
    main()
