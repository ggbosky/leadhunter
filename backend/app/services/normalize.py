"""Normalizace identifikátorů pro deduplikaci (doména, název, adresa, IČO)."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

import tldextract

# Offline extraktor – používá přibalený Public Suffix List (žádné stahování za běhu)
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# Platformy, kde identitu firmy určuje subdoména (nebo první část cesty)
SHARED_HOST_PLATFORMS = {
    "webnode.cz", "webnode.sk", "webnode.com", "wixsite.com", "wordpress.com", "blogspot.com", "estranky.cz",
    "estranky.sk", "mypage.cz", "webgarden.cz", "webgarden.com", "eshop-rychle.cz", "myshoptet.com", "squarespace.com",
    "webflow.io", "netlify.app", "github.io", "vercel.app", "business.site", "carrd.co", "weebly.com", "jimdosite.com",
    "jimdo.com", "rajce.idnes.cz", "sites.google.com", "unas.cz", "eshopy.cz", "inpage.cz", "webmium.com",
    "mozello.com", "byznysweb.cz", "wbs.cz", "websnadno.cz", "mywebsite.cz", "webooker.eu",
}
PATH_IDENTITY_HOSTS = {"wixsite.com", "sites.google.com"}

# Domény, které nejsou vlastním webem firmy (sociální sítě, katalogy, mapy, rezervace)
NON_COMPANY_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com",
    "pinterest.com", "google.com", "goo.gl", "g.page", "mapy.cz", "mapy.com", "firmy.cz", "seznam.cz",
    "zivefirmy.cz", "najisto.centrum.cz", "centrum.cz", "booking.com", "tripadvisor.com", "tripadvisor.cz",
    "airbnb.com", "airbnb.cz", "reservio.com", "reservanto.cz", "bookio.com", "noona.app", "wikipedia.org",
    "wa.me", "linktr.ee", "beacons.ai", "heureka.cz", "zbozi.cz", "foursquare.com", "yelp.com", "aliexpress.com",
    "amazon.com", "etsy.com", "fler.cz", "sashe.sk", "atlas.cz", "kurzy.cz", "rejstrik-firem.kurzy.cz",
    "openstreetmap.org", "justice.cz", "ares.gov.cz", "e-chalupy.cz", "hotel.cz", "megaubytko.cz",
    "slevomat.cz", "firmy.sk", "azet.sk", "zoznam.sk",
}
SOCIAL_PLATFORMS = {
    "facebook.com": "facebook", "fb.com": "facebook", "instagram.com": "instagram", "linkedin.com": "linkedin",
    "youtube.com": "youtube", "tiktok.com": "tiktok", "pinterest.com": "pinterest", "twitter.com": "x", "x.com": "x",
    "behance.net": "behance", "vimeo.com": "vimeo", "houzz.com": "houzz", "houzz.cz": "houzz",
}

LEGAL_SUFFIXES = [
    r"spol\.? ?s ?r\.? ?o\.?", r"s\.? ?r\.? ?o\.?", r"a\.? ?s\.?", r"v\.? ?o\.? ?s\.?", r"k\.? ?s\.?", r"z\.? ?s\.?",
    r"o\.? ?p\.? ?s\.?", r"z\.? ?ú\.?", r"se", r"s\.? ?e\.?", r"gmbh", r"ltd\.?", r"inc\.?", r"llc", r"družstvo",
]
_LEGAL_RE = re.compile(r"(,?\s+(" + "|".join(LEGAL_SUFFIXES) + r"))+\s*$", re.IGNORECASE)


def strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def ensure_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().split()[0] if url.strip() else ""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "http://" + url
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        return None
    return url


def registered_domain(host: str) -> str:
    ext = _EXTRACT(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return host.lower()


def normalize_domain(url: str | None) -> str | None:
    """Vrátí normalizovaný identifikátor webu (registrovaná doména, u sdílených platforem subdoména)."""
    url = ensure_url(url)
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    reg = registered_domain(host)
    full_platform = None
    for platform in SHARED_HOST_PLATFORMS:
        if host == platform or host.endswith("." + platform):
            full_platform = platform
            break
    if full_platform:
        if full_platform in PATH_IDENTITY_HOSTS:
            first = next((p for p in parsed.path.split("/") if p), "")
            return f"{host}/{first.lower()}" if first else host
        return host
    return reg


def is_non_company_domain(url: str | None) -> bool:
    url = ensure_url(url)
    if not url:
        return True
    host = (urlparse(url).hostname or "").lower()
    reg = registered_domain(host)
    return reg in NON_COMPANY_DOMAINS or host in NON_COMPANY_DOMAINS


def social_platform(url: str | None) -> str | None:
    url = ensure_url(url)
    if not url:
        return None
    reg = registered_domain((urlparse(url).hostname or "").lower())
    return SOCIAL_PLATFORMS.get(reg)


def is_free_builder(url: str | None) -> bool:
    url = ensure_url(url)
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return any(host.endswith("." + p) for p in SHARED_HOST_PLATFORMS)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    n = name.strip()
    n = _LEGAL_RE.sub("", n)
    n = strip_diacritics(n).lower()
    n = n.replace("&", " a ")
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_address(street: str | None, city: str | None, postcode: str | None = None) -> str | None:
    # bez ulice/čísla není adresa dostatečně jednoznačná pro deduplikaci
    if not street or not any(ch.isdigit() for ch in street):
        return None
    parts = [p for p in [street, postcode, city] if p]
    a = strip_diacritics(" ".join(parts)).lower()
    a = re.sub(r"\b(ulice|ul|nam|namesti)\b\.?", "", a)
    a = re.sub(r"[^a-z0-9 ]+", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a or None


def normalize_ico(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits or len(digits) > 8:
        return None
    digits = digits.zfill(8)
    return digits if is_valid_ico(digits) else None


def is_valid_ico(ico: str) -> bool:
    """Kontrola kontrolní číslice IČO (mod 11)."""
    if not re.fullmatch(r"\d{8}", ico):
        return False
    total = sum(int(ico[i]) * (8 - i) for i in range(7))
    rem = total % 11
    check = {0: 1, 1: 0}.get(rem, 11 - rem)
    return check == int(ico[7])


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.split(";")[0].strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if len(re.sub(r"\D", "", digits)) == 9 and not digits.startswith("+"):
        digits = "+420" + digits
    return digits if len(re.sub(r"\D", "", digits)) >= 9 else None


def normalize_linkedin(url: str | None) -> str | None:
    url = ensure_url(url)
    if not url or "linkedin.com" not in url.lower():
        return None
    p = urlparse(url)
    path = p.path.rstrip("/")
    return f"https://www.linkedin.com{path}".lower()
