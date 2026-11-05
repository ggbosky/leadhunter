"""AI poskytovatelé – lokální Ollama (preferováno, nulové náklady) nebo externí API.

Textové i multimodální (vision) modely. Pokud žádný model není dostupný,
funkce vrací None a volající moduly to musí poctivě označit (žádné vymýšlení).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

KNOWN_VISION_MODELS = ("qwen2.5vl", "qwen3-vl", "llama3.2-vision", "llava", "minicpm-v", "gemma3", "moondream",
                       "granite3.2-vision", "mistral-small3.1", "llava-llama3", "bakllava")


class LLMError(Exception):
    pass


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    elapsed_ms: int


def extract_json(text: str) -> Any:
    """Vytáhne první JSON objekt z odpovědi modelu."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        raise LLMError("Odpověď neobsahuje JSON")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"Nevalidní JSON: {exc}") from exc
    raise LLMError("Neukončený JSON")


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


class Provider:
    name = "base"
    model = ""

    def available(self) -> tuple[bool, str]:  # pragma: no cover - interface
        raise NotImplementedError

    def complete(self, system: str, prompt: str, *, images: list[Path] | None = None, json_mode: bool = False,
                 max_tokens: int = 1500, temperature: float = 0.4) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, model: str, vision: bool = False) -> None:
        self.s = get_settings()
        self.model = model
        self.vision = vision

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.s.ollama_url}/api/tags", timeout=4)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def resolve_model(self) -> str | None:
        try:
            models = self.list_models()
        except Exception:  # noqa: BLE001
            return None
        if not models:
            return None
        want = self.model
        for m in models:
            if m == want or m.split(":")[0] == want.split(":")[0] and (":" not in want or m == want):
                return m
        if self.vision:
            for m in models:
                if any(m.startswith(v) for v in KNOWN_VISION_MODELS):
                    return m
            return None
        # textový model: první, který není embedding / vision-only
        for m in models:
            if not re.search(r"embed|moondream|llava", m):
                return m
        return None

    def available(self) -> tuple[bool, str]:
        try:
            models = self.list_models()
        except Exception as exc:  # noqa: BLE001
            return False, f"Ollama neběží na {self.s.ollama_url} ({type(exc).__name__})"
        m = self.resolve_model()
        if not m:
            kind = "multimodální" if self.vision else "textový"
            return False, f"Ollama běží, ale chybí {kind} model (nainstalováno: {', '.join(models) or 'nic'}). Spusťte: ollama pull {self.model}"
        self.model = m
        return True, f"Ollama · {m}"

    def complete(self, system, prompt, *, images=None, json_mode=False, max_tokens=1500, temperature=0.4):
        msg: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            msg["images"] = [_b64(p) for p in images]
        body: dict[str, Any] = {
            "model": self.model, "stream": False,
            "messages": [{"role": "system", "content": system}, msg],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192},
        }
        if json_mode:
            body["format"] = "json"
        t0 = time.monotonic()
        try:
            r = httpx.post(f"{self.s.ollama_url}/api/chat", json=body, timeout=self.s.ollama_timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama: {exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"Ollama HTTP {r.status_code}: {r.text[:300]}")
        text = (r.json().get("message") or {}).get("content", "")
        return LLMResponse(text, self.name, self.model, int((time.monotonic() - t0) * 1000))


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str) -> None:
        self.s = get_settings()
        self.model = model

    def available(self) -> tuple[bool, str]:
        if not self.s.anthropic_api_key:
            return False, "Chybí ANTHROPIC_API_KEY"
        return True, f"Anthropic · {self.model}"

    def complete(self, system, prompt, *, images=None, json_mode=False, max_tokens=1500, temperature=0.4):
        content: list[dict[str, Any]] = []
        for p in images or []:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(p)}})
        content.append({"type": "text", "text": prompt + ("\n\nOdpověz pouze validním JSON objektem." if json_mode else "")})
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature, "system": system,
                "messages": [{"role": "user", "content": content}]}
        t0 = time.monotonic()
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=180,
                           headers={"x-api-key": self.s.anthropic_api_key, "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"})
        except httpx.HTTPError as exc:
            raise LLMError(f"Anthropic: {exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return LLMResponse(text, self.name, self.model, int((time.monotonic() - t0) * 1000))


class OpenAICompatProvider(Provider):
    """OpenAI nebo libovolné kompatibilní API (OpenRouter, LM Studio, vLLM …)."""

    name = "openai"

    def __init__(self, model: str) -> None:
        self.s = get_settings()
        self.model = model

    def available(self) -> tuple[bool, str]:
        if not self.s.openai_api_key:
            return False, "Chybí OPENAI_API_KEY"
        return True, f"OpenAI-kompatibilní API · {self.model}"

    def complete(self, system, prompt, *, images=None, json_mode=False, max_tokens=1500, temperature=0.4):
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for p in images or []:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(p)}"}})
        body: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        try:
            r = httpx.post(f"{self.s.openai_base_url.rstrip('/')}/chat/completions", json=body, timeout=180,
                           headers={"Authorization": f"Bearer {self.s.openai_api_key}"})
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI: {exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
        text = r.json()["choices"][0]["message"]["content"] or ""
        return LLMResponse(text, self.name, self.model, int((time.monotonic() - t0) * 1000))


_CACHE: dict[str, tuple[float, Provider | None, str]] = {}


def _resolve(kind: str) -> tuple[Provider | None, str]:
    s = get_settings()
    choice = s.vision_provider if kind == "vision" else s.text_provider
    order = ["ollama", "anthropic", "openai"] if choice == "auto" else [choice]
    notes = []
    for name in order:
        if name == "none":
            return None, "AI vypnuto v nastavení"
        if name == "ollama":
            p: Provider = OllamaProvider(s.ollama_vision_model if kind == "vision" else s.ollama_text_model, vision=kind == "vision")
        elif name == "anthropic":
            p = AnthropicProvider(s.anthropic_vision_model if kind == "vision" else s.anthropic_model)
        elif name == "openai":
            p = OpenAICompatProvider(s.openai_vision_model if kind == "vision" else s.openai_model)
        else:
            continue
        ok, note = p.available()
        if ok:
            return p, note
        notes.append(note)
    return None, " | ".join(notes) or "Žádný poskytovatel"


def get_provider(kind: str, use_cache: bool = True) -> tuple[Provider | None, str]:
    """kind: 'text' | 'vision'. Výsledek se cachuje 60 s."""
    now = time.time()
    if use_cache and kind in _CACHE and now - _CACHE[kind][0] < 60:
        return _CACHE[kind][1], _CACHE[kind][2]
    p, note = _resolve(kind)
    _CACHE[kind] = (now, p, note)
    return p, note


def hardware_info() -> dict[str, Any]:
    try:
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except (ValueError, OSError, AttributeError):
        ram_gb = None
    import platform
    import sys

    # NVIDIA GPU nebo Apple Silicon (sdílená paměť – Ollama využívá Metal)
    gpu = bool(shutil.which("nvidia-smi")) or (sys.platform == "darwin" and platform.machine() == "arm64")
    if ram_gb is None:
        rec = "Nelze zjistit RAM."
    elif ram_gb >= 24 or gpu:
        rec = "Doporučeno: ollama pull qwen2.5vl:7b (vision) + qwen2.5:7b-instruct (text)."
    elif ram_gb >= 12:
        rec = "Doporučeno: ollama pull qwen2.5vl:3b nebo llava:7b (vision) + qwen2.5:3b-instruct (text)."
    else:
        rec = "Málo RAM pro lokální vision model – doporučujeme externí vision API (ANTHROPIC_API_KEY / OPENAI_API_KEY)."
    return {"ram_gb": ram_gb, "cpu_count": os.cpu_count(), "nvidia_gpu": gpu, "recommendation": rec}
