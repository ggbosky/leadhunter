"""Vyhledávací API s bezplatnými kvótami (Brave Search API, Google Programmable Search).

Využívají se oficiální API s klíčem – žádný scraping výsledků vyhledávání.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlparse

from ..config import get_settings
from ..regions import REGION_BY_CODE
from ..segments import get_segment
from ..services.http_client import api_request
from ..services.normalize import is_non_company_domain, normalize_domain
from .base import AvailabilityResult, Connector, ConnectorError, DiscoveryQuery, RawCompany

# katalogy a agregátory – nejsou to weby firem
DIRECTORY_HINTS = re.compile(
    r"(firmy\.|katalog|seznam-|zlatestranky|najisto|zivefirmy|top-?\d+|nejlepsi|srovnani|recenze-|"
    r"edb\.cz|mesec\.cz|idnes|novinky|blesk|aktualne|denik|wikipedia|houzz|starmaps|svatebnicesta|"
    r"beautynity|fitnesscentra|bezrealitky|sreality|reality\.idnes|booking|ubytovani\.|e-chalupy|"
    r"profesia|jobs\.cz|prace\.cz|indeed|startupjobs)",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    parts = re.split(r"\s+[|\-–—:·»]\s+", title or "")
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return title.strip()
    # preferuj kratší část, která nevypadá jako popis služby
    generic = re.compile(r"(úvod|home|domů|vítejte|hlavní stránka|oficiální)", re.IGNORECASE)
    candidates = [p for p in parts if not generic.fullmatch(p.lower())] or parts
    return min(candidates[:3], key=len) if len(candidates) > 1 else candidates[0]


def result_to_raw(source_key: str, title: str, url: str, snippet: str, query: DiscoveryQuery) -> RawCompany | None:
    if not url or is_non_company_domain(url) or DIRECTORY_HINTS.search(url):
        return None
    dom = normalize_domain(url)
    if not dom:
        return None
    p = urlparse(url)
    homepage = f"{p.scheme}://{p.netloc}/"
    return RawCompany(
        source_key=source_key,
        external_id=dom,
        name=clean_title(title) or dom,
        segment_key=query.segment_key,
        country=query.country,
        region_code=query.region_code,
        city=query.city,
        website=homepage,
        source_url=url,
        raw={"title": title, "url": url, "snippet": snippet},
    )


def build_queries(query: DiscoveryQuery) -> list[str]:
    seg = get_segment(query.segment_key)
    city = query.city
    if not city and query.region_code in REGION_BY_CODE:
        city = REGION_BY_CODE[query.region_code].cities[0]
    city = city or ""
    if query.keyword:
        return [f"{query.keyword} {city}".strip()]
    if not seg:
        return []
    return [q.format(city=city).strip() for q in seg.search_queries]


class BraveSearchConnector(Connector):
    key = "brave"
    name = "Brave Search API"
    kind = "search"
    base_url = "https://api.search.brave.com/res/v1/web/search"
    access_policy = "Oficiální API s klíčem (bezplatný plán ~2 000 dotazů měsíčně). Respektujeme limit 1 dotaz/s."
    rate_limit_per_minute = 30

    def is_configured(self) -> bool:
        return bool(get_settings().brave_api_key)

    def check_availability(self) -> AvailabilityResult:
        if not self.is_configured():
            return AvailabilityResult("not_configured", "Chybí BRAVE_API_KEY v .env")
        try:
            r = api_request("GET", self.base_url, rate_key="brave", min_interval=self.min_interval, attempts=1,
                            params={"q": "test", "count": 1},
                            headers={"X-Subscription-Token": get_settings().brave_api_key, "Accept": "application/json"})
            return AvailabilityResult("ok" if r.status_code == 200 else "error", f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            return AvailabilityResult("unavailable", str(exc)[:300])

    def search(self, query: DiscoveryQuery) -> Iterator[RawCompany]:
        if not self.is_configured():
            raise ConnectorError("Brave Search API není nakonfigurováno")
        seen: set[str] = set()
        count = 0
        for q in build_queries(query):
            r = api_request(
                "GET", self.base_url, rate_key="brave", min_interval=self.min_interval,
                params={"q": q, "count": 20, "country": query.country.lower() if query.country in ("CZ", "SK") else "all",
                        "search_lang": "cs" if query.country == "CZ" else "sk" if query.country == "SK" else "en"},
                headers={"X-Subscription-Token": get_settings().brave_api_key, "Accept": "application/json"},
            )
            if r.status_code >= 400:
                raise ConnectorError(f"Brave HTTP {r.status_code}: {r.text[:200]}")
            for item in (r.json().get("web") or {}).get("results", []):
                raw = result_to_raw(self.key, item.get("title", ""), item.get("url", ""), item.get("description", ""), query)
                if raw and raw.external_id not in seen:
                    seen.add(raw.external_id)
                    yield raw
                    count += 1
                    if count >= query.limit:
                        return


class GoogleCseConnector(Connector):
    key = "google_cse"
    name = "Google Programmable Search (Custom Search JSON API)"
    kind = "search"
    base_url = "https://www.googleapis.com/customsearch/v1"
    access_policy = "Oficiální API s klíčem (bezplatně 100 dotazů denně)."
    rate_limit_per_minute = 20

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.google_cse_key and s.google_cse_cx)

    def check_availability(self) -> AvailabilityResult:
        if not self.is_configured():
            return AvailabilityResult("not_configured", "Chybí GOOGLE_CSE_KEY / GOOGLE_CSE_CX v .env")
        return AvailabilityResult("ok", "Klíč nastaven (dostupnost se ověří při dotazu – šetříme kvótu)")

    def search(self, query: DiscoveryQuery) -> Iterator[RawCompany]:
        if not self.is_configured():
            raise ConnectorError("Google CSE není nakonfigurováno")
        s = get_settings()
        seen: set[str] = set()
        count = 0
        for q in build_queries(query):
            for start in (1, 11):
                r = api_request("GET", self.base_url, rate_key="google_cse", min_interval=self.min_interval,
                                params={"key": s.google_cse_key, "cx": s.google_cse_cx, "q": q, "num": 10,
                                        "start": start, "gl": query.country.lower(), "hl": "cs"})
                if r.status_code >= 400:
                    raise ConnectorError(f"Google CSE HTTP {r.status_code}: {r.text[:200]}")
                items = r.json().get("items", [])
                for item in items:
                    raw = result_to_raw(self.key, item.get("title", ""), item.get("link", ""), item.get("snippet", ""), query)
                    if raw and raw.external_id not in seen:
                        seen.add(raw.external_id)
                        yield raw
                        count += 1
                        if count >= query.limit:
                            return
                if len(items) < 10:
                    break


class ManualConnector(Connector):
    key = "manual"
    name = "Ruční zadání / import CSV"
    kind = "manual"
    access_policy = "Data zadaná uživatelem."
    rate_limit_per_minute = 1000
    supports_discovery = False

    def check_availability(self) -> AvailabilityResult:
        return AvailabilityResult("ok", "Vždy dostupné")


class WebsiteConnector(Connector):
    key = "website"
    name = "Veřejné firemní weby"
    kind = "website"
    access_policy = (
        "Pouze veřejně dostupné stránky firem, respektujeme robots.txt, max. 5 stránek na web, rozestup mezi "
        "požadavky a timeouty."
    )
    rate_limit_per_minute = 30
    supports_discovery = False

    def check_availability(self) -> AvailabilityResult:
        return AvailabilityResult("ok", "Crawler je aktivní")
