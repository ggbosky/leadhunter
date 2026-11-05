"""Detekce obchodních signálů z extrahovaných dat webu a registru.

Každý signál má typ, popis, důkaz (úryvek textu / URL) a sílu 0–1.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BuyingSignal, Company, utcnow

SIGNAL_LABELS = {
    "hiring": "Nábor zaměstnanců",
    "new_branch": "Nová pobočka / provozovna",
    "new_service": "Nová služba",
    "new_product": "Nové produkty / kolekce",
    "rebranding": "Změna brandingu",
    "expansion": "Expanze / nové prostory",
    "investment": "Investice do rozvoje",
    "active_marketing": "Aktivní marketing",
    "young_company": "Mladá firma (buduje prezentaci)",
    "free_builder": "Web na šablonovém builderu",
    "outdated_site": "Dlouho neaktualizovaný web",
    "recent_activity": "Nedávná aktivita na webu",
    "eshop_growth": "E-shop s nabídkou produktů",
}
SIGNAL_STRENGTH = {
    "hiring": 0.55, "new_branch": 0.75, "new_service": 0.5, "new_product": 0.45, "rebranding": 0.7, "expansion": 0.65,
    "investment": 0.5, "active_marketing": 0.35, "young_company": 0.45, "free_builder": 0.4, "outdated_site": 0.3,
    "recent_activity": 0.3, "eshop_growth": 0.3,
}


def _fp(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:40]


def detect_signals(company: Company, extracted: dict[str, Any], registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    today = date.today()
    for stype, snippets in (extracted.get("text_signals") or {}).items():
        for sn in snippets[:2]:
            out.append({"signal_type": stype, "category": "readiness", "description": SIGNAL_LABELS.get(stype, stype),
                        "evidence": sn["snippet"], "source_url": sn.get("url"), "strength": SIGNAL_STRENGTH.get(stype, 0.4)})
    if "careers" in (extracted.get("pages_crawled") or []):
        out.append({"signal_type": "hiring", "category": "readiness", "description": "Web obsahuje sekci Kariéra / volná místa",
                    "evidence": "Nalezena stránka kariéry", "source_url": None, "strength": 0.5})
    marketing = [t for t in (extracted.get("technologies") or []) if t in ("Meta Pixel", "Seznam Sklik", "Google Tag Manager", "Hotjar")]
    if marketing:
        out.append({"signal_type": "active_marketing", "category": "readiness",
                    "description": "Na webu běží marketingové nástroje",
                    "evidence": ", ".join(marketing), "source_url": None, "strength": 0.35 + 0.05 * len(marketing)})
    latest = extracted.get("latest_date")
    if latest:
        try:
            d = date.fromisoformat(latest)
            age = (today - d).days
            if age <= 120:
                out.append({"signal_type": "recent_activity", "category": "readiness",
                            "description": "Na webu je nedávno publikovaný obsah",
                            "evidence": f"Nejnovější datum na webu: {d.strftime('%d. %m. %Y')}", "source_url": None, "strength": 0.3})
        except ValueError:
            pass
    cy = extracted.get("copyright_year")
    if cy and cy <= today.year - 4:
        out.append({"signal_type": "outdated_site", "category": "readiness", "description": SIGNAL_LABELS["outdated_site"],
                    "evidence": f"Copyright v patičce: {cy}", "source_url": None, "strength": 0.3})
    if extracted.get("uses_site_builder"):
        out.append({"signal_type": "free_builder", "category": "readiness", "description": SIGNAL_LABELS["free_builder"],
                    "evidence": f"Web běží na platformě {extracted.get('cms')}", "source_url": None, "strength": 0.4})
    if extracted.get("has_eshop"):
        out.append({"signal_type": "eshop_growth", "category": "commercial", "description": SIGNAL_LABELS["eshop_growth"],
                    "evidence": "Na webu nalezen košík / e-shop", "source_url": None, "strength": 0.3})
    founded = (registry or {}).get("founded_on") or company.founded_on
    if founded:
        try:
            fd = date.fromisoformat(founded[:10])
            yrs = (today - fd).days / 365.25
            if yrs <= 2.5:
                out.append({"signal_type": "young_company", "category": "readiness", "description": SIGNAL_LABELS["young_company"],
                            "evidence": f"Datum vzniku v ARES: {fd.strftime('%d. %m. %Y')}", "source_url": None, "strength": 0.45})
        except ValueError:
            pass
    for o in out:
        o["fingerprint"] = _fp(o["signal_type"], (o.get("evidence") or "")[:120])
    return out


def store_signals(db: Session, company: Company, signals: list[dict[str, Any]]) -> list[BuyingSignal]:
    existing = {(s.signal_type, s.fingerprint): s for s in db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == company.id))}
    keep = set()
    out = []
    for sig in signals:
        key = (sig["signal_type"], sig["fingerprint"])
        keep.add(key)
        row = existing.get(key)
        if row is None:
            row = BuyingSignal(company_id=company.id, detected_at=utcnow(), **sig)
            db.add(row)
        else:
            row.strength = sig["strength"]
            row.description = sig["description"]
        out.append(row)
    # automaticky detekované signály, které už na webu nejsou, odstraň (ruční zůstávají)
    for key, row in existing.items():
        if key not in keep and row.category != "manual":
            db.delete(row)
    db.flush()
    return out


def signal_age_factor(detected_at: datetime) -> float:
    days = (utcnow() - detected_at).days
    if days <= 60:
        return 1.0
    if days <= 180:
        return 0.75
    return 0.5
