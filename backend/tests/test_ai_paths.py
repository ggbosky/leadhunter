"""Testy AI cest s mockovaným poskytovatelem (bez sítě a bez Ollamy)."""
import json
from pathlib import Path

from PIL import Image

from app.services import llm as llm_mod
from app.services import messages as msg_mod
from app.services import vision as vision_mod
from app.services.llm import LLMResponse, extract_json


class FakeProvider:
    name = "ollama"
    model = "fake-vl"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, system, prompt, **kw):
        self.calls += 1
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return LLMResponse(text, self.name, self.model, 5)


def test_extract_json_from_chatty_output():
    assert extract_json('Tady je výsledek:\n```json\n{"a": {"b": "x}"}}\n```') == {"a": {"b": "x}"}}


def test_vision_normalization_and_missing_model(monkeypatch, tmp_path):
    from app.config import get_settings

    shot_dir = get_settings().screenshot_dir / "999"
    shot_dir.mkdir(parents=True, exist_ok=True)
    for name in ("home_desktop.jpg", "home_desktop_fold.jpg", "home_mobile.jpg", "home_mobile_fold.jpg"):
        Image.new("RGB", (400, 900), (200, 180, 160)).save(shot_dir / name)
    shots = [
        {"page": "home", "device": "desktop", "url": "https://x.cz", "path": "999/home_desktop.jpg", "fold_path": "999/home_desktop_fold.jpg"},
        {"page": "home", "device": "mobile", "url": "https://x.cz", "path": "999/home_mobile.jpg", "fold_path": "999/home_mobile_fold.jpg"},
    ]
    # bez modelu → neúplný audit, žádné vymyšlené skóre
    monkeypatch.setattr(vision_mod, "get_provider", lambda kind: (None, "žádný model"))
    res = vision_mod.analyze_visuals("X", "premium_florist", shots)
    assert res["status"] == "incomplete" and res["visual_score"] is None

    criteria = {k: {"score": 30, "observation": "o", "evidence": "e", "recommendation": "r", "confidence": 0.8}
                for k in vision_mod.CRITERIA_KEYS}
    criteria["portfolio_presentation"] = {"score": None, "confidence": 0.1}
    fake = FakeProvider({"criteria": criteria, "summary": "Zastaralý dojem", "top_issues": ["Malé fotky"],
                         "strengths": ["Kvalitní fotky práce"], "business_quality_score": 82, "design_era": "2012–2015"})
    monkeypatch.setattr(vision_mod, "get_provider", lambda kind: (fake, "ok"))
    res = vision_mod.analyze_visuals("X", "premium_florist", shots)
    assert res["status"] == "complete"
    assert 29 <= res["visual_score"] <= 31
    assert res["criteria_scored"] == 14
    assert res["business_quality_score"] == 82
    assert 0 < res["confidence"] <= 1

    # nevalidní výstup → failed (po 2 pokusech), ne vymyšlené skóre
    bad = FakeProvider("Omlouvám se, nevidím obrázek.")
    monkeypatch.setattr(vision_mod, "get_provider", lambda kind: (bad, "ok"))
    res = vision_mod.analyze_visuals("X", "premium_florist", shots)
    assert res["status"] == "failed" and res["visual_score"] is None and bad.calls == 2


def test_llm_message_generation_with_quality_retry(db, monkeypatch):
    from app.connectors.registry import ensure_data_sources
    from app.connectors.base import RawCompany
    from app.services.dedup import upsert_company

    ds = ensure_data_sources(db)
    c, _, _ = upsert_company(db, RawCompany(source_key="osm", external_id="node/llm1", name="Studio Lumen", city="Brno",
                                            website="https://studio-lumen-test.cz", segment_key="interior_design"), ds["osm"])
    good = {
        "connection_request": "Dobrý den, prohlížel jsem realizace Studia Lumen. Navrhuji weby pro interiérová studia a rád bych se spojil.",
        "first_message": "Dobrý den,\n\nna webu Studio Lumen mě zaujaly vaše realizace. Myslím, že současná prezentace neukazuje kvalitu vaší práce tak dobře, jak by mohla.\n\nMám poslat pár nápadů?",
        "follow_up": "Dobrý den, jen se připomínám. Pokud to není téma, dejte vědět.",
        "alternative": "Dobrý den, zajímalo by mě, jestli je pro Studio Lumen web aktuálně téma.",
        "pitch": "Studio Lumen má kvalitní realizace, web je neukazuje dobře.",
        "facts_used": ["company_name", "segment"],
    }
    bad = dict(good, first_message="Dobrý den, máte špatný web a zvýšíme vám tržby o 50 %.")

    class Seq(FakeProvider):
        def complete(self, system, prompt, **kw):
            self.calls += 1
            payload = bad if self.calls == 1 else good
            return LLMResponse(json.dumps(payload, ensure_ascii=False), "ollama", "fake-text", 5)

    prov = Seq(None)
    monkeypatch.setattr(msg_mod, "get_provider", lambda kind: (prov, "ok"))
    msgs = msg_mod.generate_message_set(db, c, strategy="A")
    assert prov.calls == 2  # první výstup neprošel kontrolou kvality → oprava
    first = next(m for m in msgs if m.message_type == "first_message")
    assert "špatný web" not in first.content and first.generator.startswith("llm:ollama")
    assert first.quality_warnings == []
    db.rollback()
