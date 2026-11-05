"""Deduplikace a sloučení záznamů firem.

Pořadí identifikátorů (od nejstabilnějšího):
1. IČO, 2. normalizovaná doména, 3. ID ve zdroji (např. OSM node), 4. název + město,
5. normalizovaná adresa + podobný název.
Při opakovaném nalezení se existující záznam aktualizuje – nepřepisují se ručně vyplněné údaje.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import RawCompany
from ..models import Company, CompanySource, DataSource, utcnow
from ..segments import get_segment
from .normalize import (
    ensure_url,
    is_non_company_domain,
    normalize_address,
    normalize_domain,
    normalize_ico,
    normalize_name,
    normalize_phone,
    social_platform,
)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def prepare(raw: RawCompany) -> dict:
    """Vyčistí surová data: oddělí sociální sítě od webu, normalizuje identifikátory."""
    website = ensure_url(raw.website)
    socials = dict(raw.social_links or {})
    if website and is_non_company_domain(website):
        plat = social_platform(website)
        if plat:
            socials.setdefault(plat, website)
        website = None
    domain = normalize_domain(website) if website else None
    return {
        "website": website,
        "domain": domain,
        "socials": socials,
        "ico": normalize_ico(raw.ico),
        "normalized_name": normalize_name(raw.name),
        "normalized_address": normalize_address(raw.street, raw.city, raw.postcode),
        "phone": normalize_phone(raw.phone),
        "email": (raw.email or "").strip().lower() or None,
    }


def find_existing(db: Session, raw: RawCompany, prep: dict | None = None) -> tuple[Company | None, str | None]:
    prep = prep or prepare(raw)
    if prep["ico"]:
        c = db.scalar(select(Company).where(Company.ico == prep["ico"]))
        if c:
            return c, "ico"
    if prep["domain"]:
        c = db.scalar(select(Company).where(Company.domain == prep["domain"]))
        if c:
            return c, "domain"
    src = db.scalar(
        select(CompanySource).join(DataSource).where(
            DataSource.key == raw.source_key, CompanySource.external_id == raw.external_id
        )
    )
    if src:
        return db.get(Company, src.company_id), "source_id"
    if prep["normalized_name"] and raw.city:
        candidates = db.scalars(select(Company).where(Company.normalized_name == prep["normalized_name"])).all()
        for c in candidates:
            if c.city and normalize_name(c.city) == normalize_name(raw.city):
                return c, "name_city"
    if prep["normalized_address"]:
        candidates = db.scalars(select(Company).where(Company.normalized_address == prep["normalized_address"])).all()
        for c in candidates:
            if name_similarity(c.name, raw.name) >= 0.8:
                return c, "address_name"
    if prep["phone"]:
        candidates = db.scalars(select(Company).where(Company.phone == prep["phone"])).all()
        for c in candidates:
            if name_similarity(c.name, raw.name) >= 0.7:
                return c, "phone_name"
    return None, None


def _fill(obj: Company, field: str, value) -> bool:
    if value in (None, "", {}, []):
        return False
    if getattr(obj, field) in (None, "", {}, []):
        setattr(obj, field, value)
        return True
    return False


def upsert_company(db: Session, raw: RawCompany, data_source: DataSource) -> tuple[Company, bool, str | None]:
    """Vloží nebo aktualizuje firmu. Vrací (firma, vytvořeno, typ_shody)."""
    prep = prepare(raw)
    company, match = find_existing(db, raw, prep)
    created = False
    now = utcnow()
    if company is None:
        seg = get_segment(raw.segment_key)
        company = Company(
            name=raw.name.strip()[:300],
            normalized_name=prep["normalized_name"] or raw.name.lower(),
            ico=prep["ico"],
            legal_form=raw.legal_form,
            founded_on=raw.founded_on,
            segment_key=raw.segment_key,
            tier=seg.tier if seg else None,
            country=raw.country or "CZ",
            region_code=raw.region_code,
            city=raw.city,
            street=raw.street,
            postcode=raw.postcode,
            normalized_address=prep["normalized_address"],
            lat=raw.lat,
            lon=raw.lon,
            phone=prep["phone"],
            email=prep["email"],
            website_url=prep["website"],
            domain=prep["domain"],
            social_links=prep["socials"],
            opening_hours=raw.opening_hours,
            osm_ref=raw.external_id if raw.source_key == "osm" else None,
            status="new",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(company)
        db.flush()
        created = True
    else:
        company.times_seen += 1
        company.last_seen_at = now
        # doplň chybějící údaje, nic nepřepisuj
        if prep["ico"] and not company.ico:
            clash = db.scalar(select(Company).where(Company.ico == prep["ico"], Company.id != company.id))
            if not clash:
                company.ico = prep["ico"]
        if prep["domain"] and not company.domain:
            clash = db.scalar(select(Company).where(Company.domain == prep["domain"], Company.id != company.id))
            if not clash:
                company.domain = prep["domain"]
                company.website_url = prep["website"]
        for field, value in (
            ("legal_form", raw.legal_form), ("founded_on", raw.founded_on), ("region_code", raw.region_code),
            ("city", raw.city), ("street", raw.street), ("postcode", raw.postcode), ("lat", raw.lat), ("lon", raw.lon),
            ("phone", prep["phone"]), ("email", prep["email"]), ("opening_hours", raw.opening_hours),
            ("normalized_address", prep["normalized_address"]),
        ):
            _fill(company, field, value)
        if raw.segment_key and not company.segment_key:
            company.segment_key = raw.segment_key
            seg = get_segment(raw.segment_key)
            company.tier = seg.tier if seg else None
        if prep["socials"]:
            merged = dict(company.social_links or {})
            for k, v in prep["socials"].items():
                merged.setdefault(k, v)
            company.social_links = merged
        if raw.source_key == "osm" and not company.osm_ref:
            company.osm_ref = raw.external_id

    # evidence zdroje (upsert)
    src = db.scalar(select(CompanySource).where(
        CompanySource.data_source_id == data_source.id, CompanySource.external_id == raw.external_id))
    if src is None:
        db.add(CompanySource(company_id=company.id, data_source_id=data_source.id, external_id=raw.external_id,
                             source_url=raw.source_url, raw=raw.raw, fetched_at=now))
    else:
        src.raw = raw.raw
        src.fetched_at = now
        src.source_url = raw.source_url or src.source_url
    db.flush()
    return company, created, match
