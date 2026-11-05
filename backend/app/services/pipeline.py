"""Analytická pipeline jedné firmy: crawl → registr → screenshoty → audit → vision → signály → scoring."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..connectors.ares import AresConnector
from ..connectors.registry import record_usage
from ..models import (
    Company,
    Contact,
    LeadScore,
    VisualAnalysis,
    Website,
    WebsiteAudit,
    utcnow,
)
from ..scoring.engine import HARD_DISQUALIFIERS, LeadContext, score_lead
from ..segments import classify_by_text, get_segment
from ..settings_store import get_setting
from .dedup import name_similarity
from .http_client import PoliteFetcher
from .normalize import ensure_url, is_valid_ico, normalize_domain
from .screenshots import capture_site
from .signals import detect_signals, signal_age_factor, store_signals
from .site_crawler import crawl_site
from .suppression import find_suppression
from .technical_audit import technical_audit
from .vision import analyze_visuals

log = logging.getLogger(__name__)

CONTACTED_STATUSES = {"contacted", "replied", "meeting", "won", "lost"}


def latest_website(company: Company) -> Website | None:
    if not company.websites:
        return None
    return sorted(company.websites, key=lambda w: w.last_crawled_at or w.created_at)[-1]


def latest_audit(db: Session, company: Company) -> WebsiteAudit | None:
    return db.scalar(select(WebsiteAudit).where(WebsiteAudit.company_id == company.id).order_by(WebsiteAudit.id.desc()).limit(1))


def latest_visual(db: Session, company: Company) -> VisualAnalysis | None:
    return db.scalar(select(VisualAnalysis).where(VisualAnalysis.company_id == company.id).order_by(VisualAnalysis.id.desc()).limit(1))


def current_score(db: Session, company_id: int) -> LeadScore | None:
    return db.scalar(select(LeadScore).where(LeadScore.company_id == company_id, LeadScore.is_current.is_(True))
                     .order_by(LeadScore.id.desc()).limit(1))


# ---------------------------------------------------------------------------
def _add_contact(db: Session, company: Company, name: str, role: str | None, source: str, evidence: str,
                 decision_maker: bool, verified: bool) -> Contact | None:
    name = " ".join(name.split())
    if len(name) < 4 or len(name) > 80:
        return None
    for c in company.contacts:
        if name_similarity(c.name, name) >= 0.85:
            if not c.role and role:
                c.role = role
            if verified and not c.verified:
                c.verified = True
                c.source = source
                c.source_evidence = evidence
            return c
    c = Contact(company_id=company.id, name=name, role=role, source=source, source_evidence=evidence,
                is_decision_maker=decision_maker, verified=verified)
    db.add(c)
    company.contacts.append(c)
    return c


def enrich_registry(db: Session, company: Company, extracted: dict[str, Any] | None) -> dict[str, Any]:
    """Obohacení z ARES (IČO z webu / OSM, případně přísné dohledání podle názvu)."""
    ares = AresConnector()
    info: dict[str, Any] = {}
    ico = company.ico
    if not ico and extracted:
        icos = [i for i in extracted.get("icos") or [] if is_valid_ico(i)]
        if len(icos) == 1:
            clash = db.scalar(select(Company).where(Company.ico == icos[0], Company.id != company.id))
            if not clash:
                ico = icos[0]
    try:
        if ico:
            info = ares.get_by_ico(ico) or {}
            record_usage(db, "ares", requests=1, records=1 if info else 0)
        elif company.country == "CZ":
            cands = ares.find_by_name(company.name, company.city, limit=5)
            record_usage(db, "ares", requests=1, records=len(cands))
            for cnd in cands:
                same_city = company.city and cnd.get("city") and cnd["city"].split()[0].lower() == company.city.split()[0].lower()
                if name_similarity(cnd.get("legal_name") or "", company.name) >= 0.82 and same_city and cnd.get("active"):
                    clash = db.scalar(select(Company).where(Company.ico == cnd["ico"], Company.id != company.id))
                    if not clash:
                        info = cnd
                    break
    except Exception as exc:  # noqa: BLE001
        log.warning("ARES chyba pro %s: %s", company.name, exc)
        record_usage(db, "ares", requests=1, errors=1, error=str(exc))
        return {}
    if not info:
        return {}
    company.ico = company.ico or info.get("ico")
    company.legal_name = info.get("legal_name")
    company.legal_form = info.get("legal_form")
    company.founded_on = info.get("founded_on")
    company.registry_status = "active" if info.get("active") else "inactive"
    company.nace_codes = info.get("nace") or []
    for f in ("street", "city", "postcode", "region_code"):
        if not getattr(company, f) and info.get(f):
            setattr(company, f, info[f])
    # rozhodovací osoby
    code = str(info.get("legal_form_code") or "")
    if code in ("101", "105", "107") and info.get("legal_name"):
        # OSVČ – obchodní jméno obvykle obsahuje jméno podnikatele
        nm = info["legal_name"].split(" - ")[0].split(",")[0]
        if len(nm.split()) in (2, 3) and not any(ch.isdigit() for ch in nm):
            _add_contact(db, company, nm.title() if nm.isupper() else nm, "Majitel/ka (OSVČ)", "ares",
                         f"ARES: podnikatel {info['legal_name']}, IČO {info['ico']}", True, True)
    elif code in ("112", "121", "111", "113"):
        try:
            vr = ares.statutory_persons(info["ico"])
            record_usage(db, "ares", requests=1, records=len(vr.get("persons", [])))
            info["capital_czk"] = vr.get("capital_czk")
            company.registered_capital = vr.get("capital_czk")
            for p in vr.get("persons", [])[:4]:
                _add_contact(db, company, p["name"], p["role"], "ares_vr",
                             f"Obchodní rejstřík: {p.get('organ')}, IČO {info['ico']}", True, True)
        except Exception as exc:  # noqa: BLE001
            log.info("VR nedostupný: %s", exc)
    db.flush()
    return info


def analyze_company(db: Session, company_id: int, *, screenshots: bool = True, vision: bool = True) -> dict[str, Any]:
    company = db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Firma {company_id} neexistuje")
    log_lines: list[str] = []
    result: dict[str, Any] = {"company_id": company_id, "steps": log_lines}
    extracted: dict[str, Any] = {}
    website: Website | None = None
    url = ensure_url(company.website_url)

    with PoliteFetcher() as fetcher:
        # 1) crawl
        if url:
            crawl = crawl_site(url, fetcher)
            website = db.scalar(select(Website).where(Website.company_id == company.id, Website.url == url))
            if website is None:
                website = Website(company_id=company.id, url=url)
                db.add(website)
                company.websites.append(website)
            website.final_url = crawl.final_url
            website.domain = normalize_domain(crawl.final_url or url)
            website.reachable = crawl.reachable
            website.status_code = crawl.status_code
            website.robots_allowed = crawl.robots_allowed
            website.last_crawled_at = utcnow()
            website.last_error = crawl.error
            if crawl.reachable:
                extracted = crawl.extracted
                website.https = extracted.get("https")
                website.cms = extracted.get("cms")
                website.technologies = extracted.get("technologies") or []
                website.title = (extracted.get("title") or "")[:500] or None
                website.meta_description = extracted.get("meta_description")
                website.discovered_pages = crawl.discovered
                website.text_excerpt = extracted.get("text_excerpt")
                website.extracted = {k: v for k, v in extracted.items() if k not in ("page_texts",)}
                log_lines.append(f"Web stažen ({len(crawl.pages)} stránek: {', '.join(crawl.pages)})")
                # doplň kontakty firmy
                if not company.email and extracted.get("emails"):
                    dom = company.domain or ""
                    own = [e for e in extracted["emails"] if dom and e.endswith(dom)]
                    company.email = (own or extracted["emails"])[0]
                if not company.phone and extracted.get("phones"):
                    company.phone = extracted["phones"][0]
                socials = dict(company.social_links or {})
                for k, v in (extracted.get("socials") or {}).items():
                    socials.setdefault(k, v)
                company.social_links = socials
                if not company.segment_key:
                    seg_key, hits = classify_by_text(extracted.get("text_excerpt") or "", company.name)
                    if seg_key and hits >= 2:
                        company.segment_key = seg_key
                        company.tier = get_segment(seg_key).tier
                        log_lines.append(f"Segment odhadnut z obsahu webu: {get_segment(seg_key).label}")
                for p in extracted.get("persons") or []:
                    _add_contact(db, company, p["name"], p["role"].capitalize(), "website",
                                 f"Uvedeno na webu ({p.get('page')})", True, False)
            else:
                log_lines.append(f"Web nedostupný: {crawl.error}")
            db.flush()

        # 2) registr
        registry = enrich_registry(db, company, extracted)
        if registry:
            log_lines.append(f"ARES: {registry.get('legal_name')} (IČO {registry.get('ico')})")

        # 3) screenshoty + audit
        audit = None
        if website is not None and website.reachable:
            shots_res = None
            pages = {"home": website.final_url or url}
            for k in ("services", "portfolio", "contact"):
                if (website.discovered_pages or {}).get(k):
                    pages[k] = website.discovered_pages[k]
            if screenshots:
                shots_res = capture_site(company.id, pages, fetcher)
                log_lines.append(f"Screenshoty: {len(shots_res.screenshots)} ({'; '.join(shots_res.errors) or 'bez chyb'})")
            tech = technical_audit(extracted, shots_res.metrics if shots_res else None)
            incomplete = []
            if not shots_res or not shots_res.screenshots:
                incomplete.append("Screenshoty se nepodařilo pořídit" if screenshots else "Screenshoty vypnuty")
            audit = WebsiteAudit(
                website_id=website.id, company_id=company.id, technical_score=tech["technical_score"],
                metrics={"browser": shots_res.metrics if shots_res else {}, "positives": tech["positives"],
                         "browser_measured": tech["browser_measured"],
                         "crawl": {k: extracted.get(k) for k in ("home_response_ms", "home_size_kb", "cms", "copyright_year",
                                                                 "pages_crawled", "total_word_count", "technologies")}},
                issues=tech["issues"], screenshots=shots_res.screenshots if shots_res else [],
                complete=False, incomplete_reasons=incomplete,
            )
            db.add(audit)
            db.flush()

            # 4) vision
            if vision and audit.screenshots:
                hint = (f"technické skóre {tech['technical_score']}/100; problémy: "
                        + ", ".join(i["title"] for i in tech["issues"][:6]))
                va = analyze_visuals(company.name, company.segment_key, audit.screenshots, hint)
                row = VisualAnalysis(
                    audit_id=audit.id, company_id=company.id, provider=va.get("provider", "none"), model=va.get("model"),
                    status=va["status"], visual_score=va.get("visual_score"), confidence=va.get("confidence"),
                    criteria=va.get("criteria") or [], summary=va.get("summary"), strengths=va.get("strengths") or [],
                    top_issues=va.get("top_issues") or [], error=va.get("error"), raw_response=va.get("raw_response"),
                    is_expert_estimate=True,
                )
                # doplňková data ukládáme do criteria metadat
                if va["status"] == "complete":
                    row.criteria = va["criteria"] + [{"key": "_meta", "design_era": va.get("design_era"),
                                                      "business_impression": va.get("business_impression"),
                                                      "business_quality_score": va.get("business_quality_score")}]
                db.add(row)
                if va["status"] != "complete":
                    audit.incomplete_reasons = (audit.incomplete_reasons or []) + [va.get("error") or "Vizuální analýza neproběhla"]
                    log_lines.append(f"Vizuální analýza: {va['status']} – {va.get('error')}")
                else:
                    log_lines.append(f"Vizuální analýza: {va['visual_score']}/100 ({va['provider']} {va.get('model')})")
            elif audit.screenshots:
                audit.incomplete_reasons = (audit.incomplete_reasons or []) + ["Vizuální analýza vypnuta"]
            audit.complete = not audit.incomplete_reasons
            db.flush()

        # 5) signály
        sigs = detect_signals(company, extracted, registry)
        store_signals(db, company, sigs)
        log_lines.append(f"Signály: {len(sigs)}")

    company.last_analyzed_at = utcnow()
    db.flush()
    # 6) scoring
    score = score_company(db, company, registry=registry)
    result["opportunity_score"] = score.opportunity_score
    result["category"] = score.category
    db.commit()
    return result


def build_context(db: Session, company: Company, registry: dict[str, Any] | None = None) -> LeadContext:
    website = latest_website(company)
    extracted = (website.extracted if website and website.reachable else {}) or {}
    audit = latest_audit(db, company)
    va = latest_visual(db, company)
    visual = None
    if va is not None:
        meta = next((c for c in va.criteria or [] if c.get("key") == "_meta"), {})
        visual = {"status": va.status, "visual_score": va.visual_score, "confidence": va.confidence,
                  "criteria": [c for c in va.criteria or [] if c.get("key") != "_meta"], "top_issues": va.top_issues,
                  "business_quality_score": meta.get("business_quality_score"),
                  "business_impression": meta.get("business_impression")}
    seg_cfg = get_setting(db, "segment_priorities").get(company.segment_key or "", {"enabled": True, "multiplier": 1.0})
    capital = company.registered_capital
    return LeadContext(
        company_name=company.name,
        segment_key=company.segment_key,
        country=company.country,
        has_website=bool(company.website_url),
        website_reachable=website.reachable if website else None,
        extracted=extracted,
        technical_score=audit.technical_score if audit else None,
        issues=audit.issues if audit else [],
        visual=visual,
        signals=[{"signal_type": s.signal_type, "strength": s.strength, "description": s.description,
                  "evidence": s.evidence, "age_factor": signal_age_factor(s.detected_at)} for s in company.signals],
        contacts=[{"name": c.name, "role": c.role, "linkedin_url": c.linkedin_url, "email": c.email, "phone": c.phone,
                   "is_decision_maker": c.is_decision_maker} for c in company.contacts if not c.do_not_contact],
        company_email=company.email,
        company_phone=company.phone,
        social_links=company.social_links or {},
        legal_form=company.legal_form,
        founded_on=company.founded_on,
        registry_active=None if company.registry_status is None else company.registry_status == "active",
        capital_czk=capital,
        suppressed=find_suppression(db, company=company) is not None,
        already_contacted=company.status in CONTACTED_STATUSES,
        segment_enabled=bool(seg_cfg.get("enabled", True)),
        segment_multiplier=float(seg_cfg.get("multiplier", 1.0)),
        settings_scoring=get_setting(db, "scoring"),
        pricing=get_setting(db, "pricing"),
    )


def score_company(db: Session, company: Company, registry: dict[str, Any] | None = None) -> LeadScore:
    ctx = build_context(db, company, registry)
    res = score_lead(ctx)
    db.execute(update(LeadScore).where(LeadScore.company_id == company.id, LeadScore.is_current.is_(True)).values(is_current=False))
    row = LeadScore(company_id=company.id, is_current=True, **res)
    db.add(row)
    # stav firmy (neměníme stavy obchodního procesu)
    if company.status not in CONTACTED_STATUSES:
        hard = [d for d in res["disqualification_reasons"] if d["code"] in HARD_DISQUALIFIERS]
        if hard:
            company.status = "disqualified"
            company.disqualified_reason = hard[0]["code"]
        elif company.status == "disqualified" and company.disqualified_reason not in ("do_not_contact", "duplicate", "manual"):
            company.status = "analyzed"
            company.disqualified_reason = None
        elif company.status in ("new", "analyzed", "qualified"):
            min_score = get_setting(db, "automation").get("min_score_for_messages", 60)
            company.status = "qualified" if (res["opportunity_score"] or 0) >= min_score else "analyzed"
    db.flush()
    return row
