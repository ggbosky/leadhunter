"""Discovery engine – vyhledání nových firem přes konektory a uložení do CRM."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..connectors.base import ConnectorError, DiscoveryQuery, RawCompany
from ..connectors.registry import connectors, ensure_data_sources, record_usage
from ..regions import REGION_BY_CODE
from ..segments import SEGMENTS, get_segment
from ..settings_store import get_setting
from .dedup import upsert_company
from .suppression import find_suppression

log = logging.getLogger(__name__)


@dataclass
class DiscoveryStats:
    found: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    suppressed: int = 0
    errors: list[str] = field(default_factory=list)
    company_ids: list[int] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "found": self.found, "created": self.created, "updated": self.updated, "skipped": self.skipped,
            "suppressed": self.suppressed, "errors": self.errors, "company_ids": self.company_ids[:500],
            "sources_used": self.sources_used,
        }


def store_raw(db: Session, raw: RawCompany, stats: DiscoveryStats) -> None:
    sources = ensure_data_sources(db)
    ds = sources.get(raw.source_key) or sources["manual"]
    company, created, _ = upsert_company(db, raw, ds)
    if created:
        stats.created += 1
        stats.company_ids.append(company.id)
        if find_suppression(db, company=company):
            company.status = "disqualified"
            company.disqualified_reason = "do_not_contact"
            stats.suppressed += 1
    else:
        stats.updated += 1


def run_discovery(db: Session, query: DiscoveryQuery, source_keys: list[str] | None = None,
                  max_new: int | None = None) -> DiscoveryStats:
    stats = DiscoveryStats()
    sources = ensure_data_sources(db)
    keys = source_keys or [k for k, c in connectors().items() if c.supports_discovery and c.is_configured()]
    for key in keys:
        c = connectors().get(key)
        ds = sources.get(key)
        if c is None or ds is None or not ds.enabled or not c.supports_discovery:
            continue
        if not c.is_configured():
            stats.errors.append(f"{c.name}: není nakonfigurováno")
            continue
        if key == "ares" and not query.keyword:
            continue  # ARES neumí hledat podle oboru bez klíčového slova
        stats.sources_used.append(key)
        n = 0
        try:
            for raw in c.search(query):
                stats.found += 1
                n += 1
                try:
                    with db.begin_nested():
                        store_raw(db, raw, stats)
                except Exception as exc:  # noqa: BLE001
                    stats.skipped += 1
                    log.warning("Nelze uložit %s: %s", raw.name, exc)
                if max_new is not None and stats.created >= max_new:
                    break
            record_usage(db, key, requests=1, records=n)
        except ConnectorError as exc:
            stats.errors.append(f"{c.name}: {exc}")
            record_usage(db, key, requests=1, errors=1, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Chyba konektoru %s", key)
            stats.errors.append(f"{c.name}: {type(exc).__name__}: {exc}")
            record_usage(db, key, requests=1, errors=1, error=str(exc))
        db.commit()
        if max_new is not None and stats.created >= max_new:
            break
    return stats


def plan_discovery_queries(db: Session, limit_queries: int = 12) -> list[DiscoveryQuery]:
    """Vybere kombinace segment × region podle priorit (segment multiplikátor × tier × priorita regionu)."""
    seg_prio = get_setting(db, "segment_priorities")
    reg_prio = get_setting(db, "region_priorities")
    regions = [(code, cfg["priority"]) for code, cfg in reg_prio.items() if cfg.get("enabled") and code in REGION_BY_CODE]
    segs = []
    for s in SEGMENTS:
        cfg = seg_prio.get(s.key, {"enabled": True, "multiplier": 1.0})
        if not cfg.get("enabled", True):
            continue
        tier_w = {1: 3.0, 2: 2.0, 3: 1.0}[s.tier]
        segs.append((s.key, tier_w * float(cfg.get("multiplier", 1.0))))
    combos = []
    for sk, sw in segs:
        for rc, rp in regions:
            combos.append((sw * rp, sk, rc))
    combos.sort(reverse=True)
    # rotace: preferuj kombinace, které nebyly nedávno spuštěny
    from sqlalchemy import select

    from ..models import AutomationJob

    recent = db.scalars(
        select(AutomationJob.dedupe_key).where(AutomationJob.job_type == "discover",
                                               AutomationJob.status.in_(["done", "running", "queued"]))
        .order_by(AutomationJob.id.desc()).limit(300)
    ).all()
    recent_set = set(k for k in recent if k)
    out: list[DiscoveryQuery] = []
    for _, sk, rc in combos:
        if f"discover:{sk}:{rc}" in recent_set:
            continue
        out.append(DiscoveryQuery(segment_key=sk, region_code=rc, country=REGION_BY_CODE[rc].country, limit=40,
                                  require_website=True))
        if len(out) >= limit_queries:
            break
    if not out and combos:  # vše už proběhlo – začni znovu od nejvyšší priority
        for _, sk, rc in combos[:limit_queries]:
            out.append(DiscoveryQuery(segment_key=sk, region_code=rc, country=REGION_BY_CODE[rc].country, limit=40,
                                      require_website=True))
    return out


def import_rows(db: Session, rows: list[dict], segment_key: str | None = None) -> DiscoveryStats:
    """Ruční import (CSV / formulář). Klíče: name, website, city, ico, email, phone, segment_key, region_code."""
    stats = DiscoveryStats(sources_used=["manual"])
    for i, row in enumerate(rows):
        name = (row.get("name") or row.get("nazev") or "").strip()
        website = (row.get("website") or row.get("web") or "").strip() or None
        if not name and website:
            name = website.replace("https://", "").replace("http://", "").strip("/")
        if not name:
            stats.skipped += 1
            continue
        seg = row.get("segment_key") or segment_key
        if seg and not get_segment(seg):
            seg = None
        raw = RawCompany(
            source_key="manual", external_id=(website or f"{name}|{row.get('city', '')}").lower()[:200], name=name,
            segment_key=seg, city=row.get("city") or row.get("mesto"), ico=row.get("ico"), email=row.get("email"),
            phone=row.get("phone") or row.get("telefon"), website=website, region_code=row.get("region_code"),
            country=(row.get("country") or "CZ").upper()[:2], street=row.get("street") or row.get("ulice"),
            raw={"row": i, **{k: v for k, v in row.items() if isinstance(v, (str, int, float))}},
        )
        stats.found += 1
        try:
            with db.begin_nested():
                store_raw(db, raw, stats)
        except Exception as exc:  # noqa: BLE001
            stats.skipped += 1
            stats.errors.append(f"Řádek {i + 1}: {exc}")
    db.commit()
    return stats
