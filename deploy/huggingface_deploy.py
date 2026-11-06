#!/usr/bin/env python3
"""Nasazení Lead Hunteru do Hugging Face Space (Docker) – volá GitHub Action.

Proměnné prostředí:
  HF_TOKEN       (povinné)  token Hugging Face s právem zápisu
  HF_SPACE       (volitelné) "uzivatel/nazev", výchozí "<uživatel>/leadhunter"
  HF_PRIVATE     (volitelné) "true" = soukromý Space (kód neuvidí nikdo jiný; otevírá se po přihlášení do HF)
  APP_PASSWORD   (povinné)  heslo do aplikace
  DATABASE_URL, ANTHROPIC_API_KEY, OPENAI_API_KEY, BRAVE_API_KEY, GOOGLE_CSE_KEY, GOOGLE_CSE_CX (volitelné)

  python deploy/huggingface_deploy.py            # nasadí
  python deploy/huggingface_deploy.py --dry-run  # jen připraví soubory a vypíše, co by udělal
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEYS = ["APP_PASSWORD", "DATABASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAVE_API_KEY",
               "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX"]
FRONT_MATTER = """---
title: Project Two Lead Hunter
emoji: 🎯
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: Vyhledávání a kvalifikace klientů pro Project Two
---

"""


def die(msg: str) -> None:
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"✖ {msg}")
    sys.exit(1)


def space_url(repo_id: str) -> str:
    owner, name = repo_id.split("/", 1)
    sub = re.sub(r"[^a-z0-9-]", "-", f"{owner}-{name}".lower())
    return f"https://{sub}.hf.space"


def prepare_folder() -> Path:
    """Čistý export repozitáře (jen verzované soubory) + README s konfigurací Space."""
    out = Path(tempfile.mkdtemp(prefix="hf-space-"))
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(out)], input=archive, check=True)
    readme = (out / "README.md").read_text(encoding="utf-8") if (out / "README.md").exists() else ""
    (out / "README.md").write_text(FRONT_MATTER + readme, encoding="utf-8")
    # na Space nepatří CI konfigurace ani lokální spouštěče
    for p in (".github", ".devcontainer"):
        shutil.rmtree(out / p, ignore_errors=True)
    return out


def main() -> None:
    dry = "--dry-run" in sys.argv
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token and not dry and os.environ.get("GITHUB_ACTIONS"):
        print("::warning::Nasazení přeskočeno – v GitHubu není nastaven secret HF_TOKEN. Postup je v DEPLOY.md.")
        return
    if not os.environ.get("APP_PASSWORD"):
        die("Chybí secret APP_PASSWORD (heslo do aplikace). Přidejte ho v GitHubu: Settings → Secrets and variables → Actions.")
    if not token and not dry:
        die("Chybí secret HF_TOKEN (token Hugging Face s právem Write). Viz DEPLOY.md.")
    folder = prepare_folder()
    files = sum(1 for _ in folder.rglob("*") if _.is_file())
    secrets = {k: os.environ[k] for k in SECRET_KEYS if os.environ.get(k)}
    if not secrets.get("DATABASE_URL"):
        print("⚠ DATABASE_URL není nastaveno – data se při restartu Space ztratí. Doporučujeme zdarma Neon (viz DEPLOY.md).")
    if dry:
        repo_id = os.environ.get("HF_SPACE") or "uzivatel/leadhunter"
        print(f"[dry-run] Space: {repo_id} → {space_url(repo_id)}")
        print(f"[dry-run] Souborů k nahrání: {files} (z {folder})")
        print(f"[dry-run] Secrets: {', '.join(secrets)}")
        print((folder / "README.md").read_text(encoding="utf-8")[:400])
        return

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo_id = os.environ.get("HF_SPACE", "").strip() or f"{user}/leadhunter"
    print(f"→ Space {repo_id}")
    private = os.environ.get("HF_PRIVATE", "").strip().lower() in ("1", "true", "ano", "yes")
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=private, exist_ok=True)
    if private:
        api.update_repo_settings(repo_id, private=True, repo_type="space")
    for k, v in secrets.items():
        api.add_space_secret(repo_id, k, v)
    print(f"→ Nastaveno {len(secrets)} secrets ({', '.join(secrets)})")
    api.upload_folder(folder_path=str(folder), repo_id=repo_id, repo_type="space",
                      commit_message=f"Nasazení z GitHubu {os.environ.get('GITHUB_SHA', '')[:7]}".strip(),
                      delete_patterns=["*"])
    url = space_url(repo_id)
    print(f"✓ Nahráno. Sestavení trvá cca 5–10 minut, pak aplikaci otevřete na: {url}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## Lead Hunter nasazen\n\nAplikace: **{url}**\n\nPrůběh sestavení: https://huggingface.co/spaces/{repo_id}?logs=build\n")


if __name__ == "__main__":
    main()
