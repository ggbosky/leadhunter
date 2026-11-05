"""OpenStreetMap / Overpass API konektor.

Data OSM jsou dostupná pod licencí ODbL (© přispěvatelé OpenStreetMap).
Veřejné instance Overpass mají limity – dotazy posíláme s rozestupem a
střídáme zrcadla, pokud je některé nedostupné.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator

import httpx

from ..config import get_settings
from ..regions import REGION_BY_CODE, region_from_city, region_from_postcode
from ..segments import SEGMENTS, Segment, get_segment
from ..services.http_client import RetryableStatus, api_request
from .base import AvailabilityResult, Connector, ConnectorError, DiscoveryQuery, RawCompany

log = logging.getLogger(__name__)

NAME_REGEX_KEYS = ("shop", "craft", "office", "amenity", "leisure", "tourism", "healthcare")


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_query(segment: Segment | None, query: DiscoveryQuery, limit: int) -> str:
    if query.city:
        area = (
            f'area["ISO3166-1"="{_q(query.country)}"][admin_level=2]->.c;\n'
            f'rel(area.c)["boundary"="administrative"]["name"="{_q(query.city)}"]["admin_level"~"^(4|6|7|8)$"];\n'
            "map_to_area->.a;\n"
        )
    elif query.region_code:
        area = f'area["ISO3166-2"="{_q(query.region_code)}"]->.a;\n'
    else:
        area = f'area["ISO3166-1"="{_q(query.country)}"][admin_level=2]->.a;\n'

    segs = [segment] if segment else [s for s in SEGMENTS if s.tier == 1]
    stmts: list[str] = []
    website_filter = ""  # web filtrujeme v Pythonu (website / contact:website / url)
    for seg in segs:
        for k, v in seg.osm_tags:
            stmts.append(f'nwr["{_q(k)}"="{_q(v)}"]["name"]{website_filter}(area.a);')
        if seg.name_regex:
            for k in NAME_REGEX_KEYS:
                stmts.append(f'nwr["name"~"{_q(seg.name_regex)}",i]["{k}"]{website_filter}(area.a);')
    if query.keyword:
        stmts.append(f'nwr["name"~"{_q(query.keyword)}",i](area.a);')
    body = "\n  ".join(stmts)
    return f"[out:json][timeout:90];\n{area}(\n  {body}\n);\nout center tags {limit};"


def _segment_for_tags(tags: dict, hinted: str | None) -> str | None:
    if hinted:
        return hinted
    name = tags.get("name", "")
    for seg in SEGMENTS:
        for k, v in seg.osm_tags:
            if tags.get(k) == v:
                return seg.key
        if seg.name_regex and re.search(seg.name_regex, name, re.IGNORECASE):
            return seg.key
    return None


def element_to_raw(el: dict, segment_key: str | None, country: str) -> RawCompany | None:
    tags = el.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None
    # řetězce / franšízy nejsou cílová skupina
    if tags.get("brand:wikidata") or tags.get("operator:wikidata"):
        return None
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    street = tags.get("addr:street") or tags.get("addr:place")
    num = tags.get("addr:housenumber") or "/".join(
        x for x in [tags.get("addr:conscriptionnumber"), tags.get("addr:streetnumber")] if x
    )
    if street and num:
        street = f"{street} {num}"
    city = tags.get("addr:city")
    postcode = tags.get("addr:postcode")
    socials = {}
    for key, platform in (("contact:facebook", "facebook"), ("facebook", "facebook"), ("contact:instagram", "instagram"),
                          ("instagram", "instagram"), ("contact:linkedin", "linkedin"), ("contact:youtube", "youtube")):
        if tags.get(key):
            socials[platform] = tags[key]
    ico = tags.get("ref:ico") or tags.get("ico") or tags.get("company:ico") or tags.get("ref:IČO")
    seg = _segment_for_tags(tags, segment_key)
    region = region_from_postcode(postcode) or region_from_city(city)
    return RawCompany(
        source_key="osm",
        external_id=f"{el.get('type')}/{el.get('id')}",
        name=name.strip(),
        segment_key=seg,
        country=country,
        region_code=region,
        city=city,
        street=street,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile"),
        email=tags.get("email") or tags.get("contact:email"),
        website=tags.get("website") or tags.get("contact:website") or tags.get("url"),
        ico=ico,
        social_links=socials,
        opening_hours=tags.get("opening_hours"),
        source_url=f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        raw={"tags": tags},
    )


class OverpassConnector(Connector):
    key = "osm"
    name = "OpenStreetMap (Overpass API)"
    kind = "map"
    base_url = "https://overpass-api.de/api/interpreter"
    access_policy = (
        "Otevřená data OpenStreetMap pod licencí ODbL (© přispěvatelé OpenStreetMap). Veřejné Overpass instance – "
        "dodržujeme fair-use: max. několik dotazů za minutu, timeouty a střídání zrcadel."
    )
    rate_limit_per_minute = 4

    def __init__(self) -> None:
        self.urls = get_settings().overpass_url_list

    def _post(self, query: str, timeout: float = 120.0) -> dict:
        errors = []
        for url in self.urls:
            try:
                r = api_request("POST", url, rate_key="overpass", min_interval=self.min_interval, attempts=2,
                                timeout=timeout, data={"data": query})
                if r.status_code == 200:
                    return r.json()
                errors.append(f"{url}: HTTP {r.status_code}")
            except (httpx.HTTPError, RetryableStatus, ValueError) as exc:
                errors.append(f"{url}: {exc}")
                continue
        raise ConnectorError("Overpass nedostupný: " + "; ".join(errors))

    def check_availability(self) -> AvailabilityResult:
        if get_settings().disable_network:
            return AvailabilityResult("unavailable", "Síť je vypnutá")
        errors = []
        for url in self.urls:
            status_url = url.replace("/interpreter", "/status")
            try:
                r = api_request("GET", status_url, rate_key="overpass-status", min_interval=1, attempts=1, timeout=15)
                if r.status_code == 200:
                    return AvailabilityResult("ok", f"Dostupné zrcadlo: {url}")
                errors.append(f"{url}: HTTP {r.status_code}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {type(exc).__name__}")
        return AvailabilityResult("unavailable", "; ".join(errors))

    def search(self, query: DiscoveryQuery) -> Iterator[RawCompany]:
        segment = get_segment(query.segment_key)
        if query.region_code and query.region_code in REGION_BY_CODE:
            query.country = REGION_BY_CODE[query.region_code].country
        q = build_query(segment, query, limit=max(query.limit * 4, 100))
        data = self._post(q)
        count = 0
        for el in data.get("elements", []):
            raw = element_to_raw(el, query.segment_key, query.country)
            if raw is None:
                continue
            if query.require_website and not raw.website:
                continue
            if not raw.region_code:
                raw.region_code = query.region_code
            if not raw.city and query.city:
                raw.city = query.city
            yield raw
            count += 1
            if count >= query.limit:
                break
