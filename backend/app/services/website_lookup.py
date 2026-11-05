"""Dohledání webu k firmám, které ho v datech nemají (typicky firmy z ARES nebo OSM bez tagu website).

Postup:
1. kandidátní domény odvozené z názvu firmy (truhlarstvi-hanus.cz, truhlarstvihanus.cz …),
2. výsledky vyhledávacího API (Brave / Google CSE), pokud je nakonfigurováno.

Každý kandidát se OVĚŘUJE – web musí obsahovat IČO firmy (spolehlivé), nebo, pokud IČO neznáme,
název firmy v titulku/nadpisu a zároveň město v textu. Neověřený web se nepřiřadí.
"""
from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from ..connectors.base import DiscoveryQuery
from ..connectors.registry import connectors
from ..models import Company
from .http_client import BlockedByPolicy, PoliteFetcher
from .normalize import is_non_company_domain, normalize_domain, normalize_name, strip_diacritics
from .site_crawler import discover_pages, extract_page

log = logging.getLogger(__name__)

# slova, která v doméně často chybí (právní formy řeší normalize_name)
STOP_WORDS = {"a", "s", "spol", "the", "cz", "studio", "group", "company", "firma"}


@dataclass
class LookupResult:
    url: str | None
    domain: str | None
    method: str  # ico | name_city | none
    candidates_checked: int
    evidence: str = ""


def domain_candidates(name: str, country: str = "CZ", limit: int = 8) -> list[str]:
    base = normalize_name(name)
    # odstraň obsah za pomlčkou typu "Fischer - Truhlářství" zachovej obě varianty
    words = [w for w in re.split(r"\s+", base) if w and w not in STOP_WORDS]
    if not words:
        return []
    tlds = {"CZ": ["cz"], "SK": ["sk"]}.get(country, []) + ["com", "eu"]
    stems: list[str] = []
    for variant in (words, words[:3], words[-2:] if len(words) > 2 else words):
        joined = "".join(variant)
        dashed = "-".join(variant)
        for s in (joined, dashed):
            if 3 <= len(s) <= 40 and s not in stems:
                stems.append(s)
    out: list[str] = []
    for stem in stems:
        for tld in tlds:
            d = f"{stem}.{tld}"
            if d not in out:
                out.append(d)
    return out[:limit]


def _resolves(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, 443)
        return True
    except (socket.gaierror, UnicodeError):
        return False


BOT_CHALLENGE_RE = re.compile(r"(verifying your browser|checking your browser|just a moment|cf-challenge|"
                              r"ddos protection|captcha|ověřujeme váš prohlížeč)", re.I)


def _fetch_any(url: str, fetcher: PoliteFetcher):
    """Zkusí https a při chybě spojení/certifikátu i http (staré weby často HTTPS nemají)."""
    variants = [url]
    if url.startswith("https://"):
        variants.append("http://" + url[len("https://"):])
    last = "nedostupné"
    for v in variants:
        try:
            r = fetcher.get(v, attempts=1)
            return r, None
        except BlockedByPolicy as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001
            last = type(exc).__name__
    return None, last


def verify_site(url: str, company: Company, fetcher: PoliteFetcher) -> tuple[str | None, str, str | None]:
    """Vrátí (metoda ověření, důkaz, finální URL) nebo (None, důvod, None)."""
    r, err = _fetch_any(url, fetcher)
    if r is None:
        return None, err or "nedostupné", None
    if r.status_code >= 400 or "<html" not in r.text[:3000].lower():
        return None, f"HTTP {r.status_code}", None
    if is_non_company_domain(r.final_url):
        return None, "přesměrováno na katalog / sociální síť", None
    if BOT_CHALLENGE_RE.search(r.text[:5000]) and len(r.text) < 20000:
        return None, "web je chráněn proti robotům – nelze automaticky ověřit (neobcházíme)", None
    pages = [extract_page(r.text, r.final_url)]
    if company.ico and company.ico not in pages[0]["icos"]:
        contact = discover_pages(BeautifulSoup(r.text, "lxml"), r.final_url).get("contact")
        if contact:
            try:
                rc = fetcher.get(contact, attempts=1)
                if rc.status_code < 400:
                    pages.append(extract_page(rc.text, rc.final_url))
            except Exception:  # noqa: BLE001
                pass
    icos = {i for p in pages for i in p["icos"]}
    if company.ico:
        if company.ico in icos:
            return "ico", f"IČO {company.ico} uvedeno na {r.final_url}", r.final_url
        if icos:
            return None, f"web uvádí jiné IČO ({', '.join(sorted(icos))})", None
    # web IČO neuvádí: název v titulku/H1 + (město nebo jméno osoby z rejstříku) v textu
    head = normalize_name(" ".join([pages[0].get("title") or ""] + (pages[0].get("h1") or [])))
    core = [w for w in normalize_name(company.name).split() if w not in STOP_WORDS and len(w) > 2]
    text = strip_diacritics(" ".join(p.get("text") or "" for p in pages)).lower()
    if not core or not all(w in head for w in core):
        return None, "web nepatří k firmě (neshoda názvu/IČO)", None
    city = strip_diacritics((company.city or "").split()[0]).lower() if company.city else ""
    persons = [strip_diacritics(c.name).lower() for c in company.contacts if c.source in ("ares", "ares_vr")]
    surnames = {p.split()[-1] for p in persons if p.split()}
    person_hit = next((p for p in persons if p in text), None) or next((sn for sn in surnames if len(sn) > 3 and sn in text), None)
    if person_hit and company.ico:
        return "name_person", f"název firmy v titulku webu a osoba z obchodního rejstříku ({person_hit}) v textu", r.final_url
    if len(core) >= 2 and city and city in text:
        return "name_city", f"název „{company.name}“ v titulku webu a město {company.city} v textu", r.final_url
    return None, "název sedí, ale chybí další potvrzení (IČO, město nebo jednatel) – neověřeno", None


def find_website(company: Company, fetcher: PoliteFetcher, use_search_api: bool = True, max_checks: int = 10) -> LookupResult:
    checked = 0
    seen: set[str] = set()
    candidates: list[str] = []
    for d in domain_candidates(company.name, company.country):
        if _resolves(d):
            candidates.append(f"https://{d}/")
    if use_search_api:
        for key in ("brave", "google_cse"):
            c = connectors().get(key)
            if c is None or not c.is_configured():
                continue
            try:
                q = DiscoveryQuery(keyword=f'"{company.name}"', city=company.city, country=company.country, limit=5)
                for raw in c.search(q):
                    if raw.website:
                        candidates.append(raw.website)
            except Exception as exc:  # noqa: BLE001
                log.info("Vyhledávací API selhalo: %s", exc)
            break
    for url in candidates:
        dom = normalize_domain(url)
        if not dom or dom in seen:
            continue
        seen.add(dom)
        checked += 1
        method, evidence, final_url = verify_site(url, company, fetcher)
        if method:
            return LookupResult(url=final_url or url, domain=normalize_domain(final_url or url) or dom, method=method, candidates_checked=checked, evidence=evidence)
        if checked >= max_checks:
            break
    return LookupResult(url=None, domain=None, method="none", candidates_checked=checked,
                        evidence="Web se nepodařilo dohledat a ověřit")


def lookup_summary(res: LookupResult) -> dict[str, Any]:
    return {"url": res.url, "domain": res.domain, "method": res.method, "checked": res.candidates_checked,
            "evidence": res.evidence}
