"""Visual Intelligence Engine – AI hodnocení vizuální kvality webu ze screenshotů.

Pokud multimodální model není dostupný, vizuální hodnocení se NEVYMÝŠLÍ:
analýza se uloží se stavem "incomplete" a skóre None.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..segments import get_segment
from .llm import LLMError, extract_json, get_provider

log = logging.getLogger(__name__)

CRITERIA: list[tuple[str, str, float]] = [
    ("aesthetic_quality", "Celková estetická kvalita", 1.4),
    ("modernity", "Modernost grafického designu", 1.3),
    ("typography", "Typografie", 1.0),
    ("color_palette", "Barevná paleta", 0.9),
    ("visual_hierarchy", "Vizuální hierarchie", 1.0),
    ("layout", "Kvalita layoutu", 1.0),
    ("hero_section", "Kvalita hero sekce", 1.1),
    ("photography", "Kvalita fotografií", 1.1),
    ("brand_consistency", "Konzistence brandingu", 0.9),
    ("mobile_design", "Mobilní design", 1.2),
    ("offer_clarity", "Přehlednost nabídky", 1.0),
    ("visual_trust", "Vizuální důvěryhodnost", 1.0),
    ("portfolio_presentation", "Prezentace portfolia", 0.9),
    ("cta_quality", "Kvalita CTA", 0.9),
    ("audience_fit", "Vhodnost designu pro cílovou skupinu", 1.1),
]
CRITERIA_KEYS = [c[0] for c in CRITERIA]

SYSTEM = (
    "Jsi zkušený art director a UX/UI designér, který hodnotí firemní weby pro českou webovou agenturu. "
    "Hodnotíš pouze to, co je skutečně vidět na přiložených screenshotech. Nic si nevymýšlíš. "
    "Pokud něco na screenshotech není vidět (např. portfolio), nastav score na null a confidence nízko. "
    "Buď konkrétní – popisuj viditelné prvky (barvy, písma, rozložení, fotky, texty tlačítek). "
    "Piš česky. Odpovídej výhradně validním JSON."
)


def build_prompt(company_name: str, segment_label: str | None, shots: list[dict[str, Any]], tech_hint: str) -> str:
    shot_desc = "\n".join(f"- Obrázek {i + 1}: {s['page']} / {s['device']} ({s['url']})" for i, s in enumerate(shots))
    crit = "\n".join(f'  "{k}": {{"score": 0-100 nebo null, "observation": "...", "evidence": "co přesně je vidět", '
                     f'"recommendation": "...", "confidence": 0-1}}' for k, _, _ in CRITERIA)
    names = "\n".join(f"- {k}: {label}" for k, label, _ in CRITERIA)
    return f"""Firma: {company_name}
Obor: {segment_label or 'neznámý'}
Screenshoty:
{shot_desc}

Doplňující objektivní měření (nehodnoť je znovu, slouží jako kontext): {tech_hint}

Ohodnoť web podle 15 kritérií (0 = velmi slabé, 50 = průměrné/zastaralé, 75 = solidní moderní web, 90+ = špičková prémiová prezentace):
{names}

Odpověz JSON objektem v tomto tvaru:
{{
 "criteria": {{
{crit}
 }},
 "design_era": "odhad období, kdy design vznikl (např. 2010–2014)",
 "summary": "2–3 věty celkového dojmu",
 "strengths": ["..."],
 "top_issues": ["nejdůležitější vizuální problémy, max 5, konkrétně"],
 "business_impression": "jak kvalitně působí samotná firma/práce podle fotek a obsahu (ne podle designu webu)",
 "business_quality_score": 0-100 nebo null
}}"""


def _num(v: Any, lo: float = 0, hi: float = 100) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, f))


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    crit_in = data.get("criteria") or {}
    criteria = []
    weighted = 0.0
    wsum = 0.0
    confs = []
    for key, label, weight in CRITERIA:
        c = crit_in.get(key) or {}
        if not isinstance(c, dict):
            c = {"score": c}
        score = _num(c.get("score"))
        conf = _num(c.get("confidence"), 0, 1)
        if conf is None:
            conf = 0.5 if score is not None else 0.0
        criteria.append({
            "key": key, "label": label, "score": score, "observation": (c.get("observation") or "")[:600],
            "evidence": (c.get("evidence") or "")[:600], "recommendation": (c.get("recommendation") or "")[:600],
            "confidence": round(conf, 2), "weight": weight,
        })
        if score is not None:
            w = weight * (0.5 + conf / 2)
            weighted += score * w
            wsum += w
            confs.append(conf)
    scored = sum(1 for c in criteria if c["score"] is not None)
    visual_score = round(weighted / wsum, 1) if wsum else None
    coverage = scored / len(CRITERIA)
    confidence = round((sum(confs) / len(confs) if confs else 0) * (0.4 + 0.6 * coverage), 2)
    return {
        "criteria": criteria,
        "visual_score": visual_score,
        "confidence": confidence,
        "summary": (data.get("summary") or "")[:1500],
        "strengths": [str(x)[:300] for x in (data.get("strengths") or [])][:6],
        "top_issues": [str(x)[:300] for x in (data.get("top_issues") or [])][:6],
        "design_era": (data.get("design_era") or "")[:60] or None,
        "business_impression": (data.get("business_impression") or "")[:800] or None,
        "business_quality_score": _num(data.get("business_quality_score")),
        "criteria_scored": scored,
    }


def select_images(shots: list[dict[str, Any]], max_images: int = 4) -> list[dict[str, Any]]:
    order = [("home", "desktop"), ("home", "mobile"), ("portfolio", "desktop"), ("services", "desktop"), ("contact", "desktop")]
    out = []
    for page, device in order:
        for s in shots:
            if s["page"] == page and s["device"] == device:
                out.append(s)
    return out[:max_images]


def analyze_visuals(company_name: str, segment_key: str | None, shots: list[dict[str, Any]],
                    tech_hint: str = "") -> dict[str, Any]:
    """Vrací dict se stavem complete / incomplete / failed."""
    s = get_settings()
    if not shots:
        return {"status": "incomplete", "provider": "none", "model": None, "visual_score": None,
                "error": "Nejsou k dispozici žádné screenshoty."}
    provider, note = get_provider("vision")
    if provider is None:
        return {"status": "incomplete", "provider": "none", "model": None, "visual_score": None,
                "error": f"Multimodální model není dostupný ({note}). Vizuální hodnocení nebylo provedeno – "
                         "použity pouze technické metriky."}
    seg = get_segment(segment_key)
    chosen = select_images(shots, max_images=4 if provider.name != "ollama" else 3)
    # pro vision model posíláme "above the fold" výřezy (menší, rychlejší) + celou stránku homepage
    paths: list[Path] = []
    for sh in chosen:
        rel = sh.get("fold_path") if sh["device"] == "mobile" or sh["page"] != "home" else sh["path"]
        p = s.screenshot_dir / (rel or sh["path"])
        if p.exists():
            paths.append(_downscale(p))
    if not paths:
        return {"status": "incomplete", "provider": provider.name, "model": provider.model, "visual_score": None,
                "error": "Soubory screenshotů nebyly nalezeny."}
    prompt = build_prompt(company_name, seg.label if seg else None, chosen, tech_hint)
    last_err = None
    for attempt in range(2):
        try:
            resp = provider.complete(SYSTEM, prompt, images=paths, json_mode=True, max_tokens=3000, temperature=0.2)
            data = extract_json(resp.text)
            norm = normalize_result(data)
            if norm["criteria_scored"] < 5:
                raise LLMError(f"Model ohodnotil jen {norm['criteria_scored']} kritérií")
            return {"status": "complete", "provider": provider.name, "model": resp.model, "raw_response": resp.text[:20000],
                    "elapsed_ms": resp.elapsed_ms, **norm}
        except LLMError as exc:
            last_err = str(exc)
            log.warning("Vision pokus %s selhal: %s", attempt + 1, exc)
    return {"status": "failed", "provider": provider.name, "model": provider.model, "visual_score": None,
            "error": f"Vision model nevrátil použitelné hodnocení: {last_err}"}


def _downscale(path: Path, max_side: int = 1600) -> Path:
    """Zmenší dlouhé screenshoty (šetří tokeny / VRAM)."""
    try:
        from PIL import Image
    except ImportError:
        return path
    out = path.with_name(path.stem + "_ai.jpg")
    if out.exists():
        return out
    try:
        img = Image.open(path).convert("RGB")
        w, h = img.size
        if h > w * 2.2:  # velmi dlouhá stránka – ořízni na horní část
            img = img.crop((0, 0, w, int(w * 2.2)))
        img.thumbnail((max_side, max_side))
        img.save(out, "JPEG", quality=80)
        return out
    except Exception:  # noqa: BLE001
        return path
