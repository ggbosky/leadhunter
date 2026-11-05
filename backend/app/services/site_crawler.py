"""Crawler firemních webů a extrakce obchodních informací.

Stahuje pouze veřejné stránky (respektuje robots.txt), max. několik stránek na web,
a z HTML vytahuje fakta, která slouží jako důkazy pro scoring a personalizaci zpráv.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urljoin, urldefrag, urlparse

from bs4 import BeautifulSoup

from ..config import get_settings
from .http_client import BlockedByPolicy, FetchError, PoliteFetcher
from .normalize import is_valid_ico, normalize_phone, registered_domain, social_platform

log = logging.getLogger(__name__)

PAGE_PATTERNS: dict[str, re.Pattern] = {
    "services": re.compile(r"(slu[zž]by|nab[ií]dk|co-?d[eě]l[aá]me|services|what-we-do|o[sš]et[rř]en|procedur|"
                           r"sortiment|produkty|kuchyn[eě]|n[aá]bytek|lekce|kurzy|treatments|our-services)", re.I),
    "portfolio": re.compile(r"(portfolio|realizac|reference|galerie|gallery|projekty|projects|na[sš]e-?pr[aá]ce|"
                            r"works|fotogalerie|svatby|interi[eé]ry|uk[aá]zky)", re.I),
    "contact": re.compile(r"(kontakt|contact|kde-n[aá]s-najdete|napi[sš]te)", re.I),
    "about": re.compile(r"(o-?n[aá]s|about|o-?mn[eě]|kdo-jsme|n[aá][sš]-t[yý]m|team|p[rř][ií]b[eě]h)", re.I),
    "pricing": re.compile(r"(cen[ií]k|ceny|pricing|price|cennik)", re.I),
    "careers": re.compile(r"(kari[eé]r|voln[aá]-m[ií]sta|pr[aá]ce-u-n[aá]s|hled[aá]me|jobs|careers|pozice)", re.I),
    "blog": re.compile(r"(blog|aktuality|novinky|news|magaz[ií]n|clanky|články)", re.I),
}
PAGE_FETCH_ORDER = ["services", "portfolio", "contact", "about", "pricing", "careers", "blog"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+|00)?(?:420|421)?[\s ]?[1-9]\d{2}[\s ]?\d{3}[\s ]?\d{3}\b")
ICO_RE = re.compile(r"I[ČC]O?\s*[:.]?\s*(\d{2}\s?\d{2}\s?\d{2}\s?\d{2}|\d{6,8})", re.I)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|\(c\)|copyright)\s*(?:\w+\s+)?((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))?", re.I)
PRICE_RE = re.compile(r"(\d{1,3}(?:[  .]\d{3})+|\d{2,7})\s*(?:,-|,–|\.-)?\s*(Kč|CZK|€|EUR)\b", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\b")
YEARS_EXP_RE = re.compile(r"(\d{1,2})\s*(?:\+\s*)?let(?:é|y)?\s+(?:zkušeností|na trhu|praxe|tradice|v oboru|působení)", re.I)
SINCE_RE = re.compile(r"(?:od roku|založen[aoý]?\s+(?:v\s+)?(?:roce\s+)?|since|fungujeme od|tradice od)\s*((?:19|20)\d{2})", re.I)
PERSON_ROLE_RE = re.compile(
    r"((?i:majitel(?:ka)?|zakladatel(?:ka)?|spoluzakladatel(?:ka)?|jednatel(?:ka)?|founder|co-founder|owner|ceo|"
    r"ředitel(?:ka)?|provozovatel(?:ka)?|hlavní designér(?:ka)?|architekt(?:ka)?|floristka|fotograf(?:ka)?))"
    r"[\s:,–\-]+((?:Ing\.|Mgr\.|MgA\.|Bc\.|MUDr\.|Ing\. arch\.)?\s?[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+\s[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+(?:ová)?)",
)
PERSON_ROLE_REV_RE = re.compile(
    r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+\s[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+)\s*[,–\-|]\s*"
    r"((?i:majitel(?:ka)?|zakladatel(?:ka)?|spoluzakladatel(?:ka)?|jednatel(?:ka)?|founder|owner|ceo|ředitel(?:ka)?))",
)

TEXT_SIGNALS: dict[str, re.Pattern] = {
    "hiring": re.compile(r"(hledáme\s+(?:\w+\s+){0,3}?(?:kolegu|kolegyni|kolegy|posilu|posily|zaměstnanc\w*|pracovník\w*|"
                         r"brigádník\w*|do (?:našeho )?týmu|na pozici)|přijmeme\s+(?:\w+\s+){0,2}?(?:\w+(?:ka|ku|ce|ře|tele|íka))\b|"
                         r"volná (?:pracovní )?místa|volné (?:pracovní )?pozice|nabídka práce|připoj(?:te)? se k (?:našemu )?týmu|"
                         r"rozšiřujeme (?:náš )?tým|we.?re hiring)", re.I),
    "new_branch": re.compile(r"(nov(?:ou|á|é|ého) poboč\w*|otevíráme|otevřeli jsme|nově otevřen\w*|druhou poboč\w*|"
                             r"nová provozovna|nové studio|nový showroom)", re.I),
    "new_service": re.compile(r"(nově nabízíme|nová služba|nově v nabídce|nově u nás|novinka v nabídce|nově poskytujeme)", re.I),
    "new_product": re.compile(r"(nová kolekce|nové produkty|představujeme|uvádíme na trh|limitovaná edice|novinky v e-shopu)", re.I),
    "rebranding": re.compile(r"(nové logo|nová vizuální identita|rebranding|nový název|přejmenovali jsme|změna názvu)", re.I),
    "expansion": re.compile(r"(expanze|rozšiřujeme|rozšířili jsme|nové prostory|větší prostory|stěhujeme se|"
                            r"přestěhovali jsme se|nová výrobní hala)", re.I),
    "investment": re.compile(r"(investovali jsme|nové vybavení|nový stroj|modernizace provozu|dotace|evropská unie|"
                             r"spolufinancován\w*)", re.I),
}
QUALITY_PATTERNS: dict[str, re.Pattern] = {
    "testimonials": re.compile(r"(recenze|reference klient|hodnocení|co o nás říkají|říkají o nás|spokojen[íý] klient|testimonial|★★★)", re.I),
    "awards": re.compile(r"(ocenění|oceněn[aáý]|vítěz\w*|award|finalist\w*|nominace|cena\s+\w+\s+20\d{2})", re.I),
    "press": re.compile(r"(napsali o nás|média o nás|v médiích|publikováno v|psali o nás|as seen in|press)", re.I),
    "premium": re.compile(r"(luxusní|prémiov\w*|exkluzivn\w*|na míru|high.?end|designov\w*|butik\w*|boutique|vip\b|"
                          r"ruční výrob\w*|ručně vyráběn\w*|řemesln\w*|manufaktur\w*|individuální přístup)", re.I),
    "weddings": re.compile(r"(svatb\w*|wedding)", re.I),
    "b2b": re.compile(r"(pro firmy|firemní klient|b2b|velkoobchod|pro architekty|pro developery)", re.I),
    "team": re.compile(r"(náš tým|našeho týmu|tým \d+|\d+\s+(?:zaměstnanců|specialistů|odborníků|kolegů))", re.I),
    "branches": re.compile(r"(poboč\w+|provozovn\w+|showroom\w*)", re.I),
}
TECH_PATTERNS: dict[str, re.Pattern] = {
    "WordPress": re.compile(r"wp-content|wp-includes", re.I),
    "WooCommerce": re.compile(r"woocommerce", re.I),
    "Wix": re.compile(r"wix\.com|_wixCIDX|wixstatic", re.I),
    "Webnode": re.compile(r"webnode", re.I),
    "Shoptet": re.compile(r"shoptet", re.I),
    "Upgates": re.compile(r"upgates", re.I),
    "Eshop-rychle": re.compile(r"eshop-rychle", re.I),
    "Shopify": re.compile(r"cdn\.shopify|shopify\.com", re.I),
    "PrestaShop": re.compile(r"prestashop", re.I),
    "Squarespace": re.compile(r"squarespace", re.I),
    "Webflow": re.compile(r"webflow", re.I),
    "Joomla": re.compile(r"/media/jui/|joomla", re.I),
    "Drupal": re.compile(r"drupal", re.I),
    "Next.js": re.compile(r"/_next/static", re.I),
    "Elementor": re.compile(r"elementor", re.I),
    "Divi": re.compile(r"et_pb_|divi", re.I),
    "Bootstrap": re.compile(r"bootstrap(\.min)?\.(css|js)", re.I),
    "jQuery": re.compile(r"jquery[.-]?(\d+\.\d+)?", re.I),
    "Flash": re.compile(r"\.swf\b|shockwave", re.I),
    "Google Analytics": re.compile(r"gtag\(|google-analytics\.com|googletagmanager\.com/gtag", re.I),
    "Google Tag Manager": re.compile(r"googletagmanager\.com/gtm", re.I),
    "Meta Pixel": re.compile(r"connect\.facebook\.net/.+/fbevents|fbq\(", re.I),
    "Seznam Sklik": re.compile(r"c\.seznam\.cz/js/rc\.js|sklik", re.I),
    "Hotjar": re.compile(r"hotjar", re.I),
    "Smartsupp": re.compile(r"smartsupp", re.I),
    "Cookie lišta": re.compile(r"cookiebot|cookieconsent|cookie-law|complianz|cookieyes", re.I),
}
BOOKING_PATTERNS = re.compile(r"(reservio|reservanto|bookio|noona|calendly|simplybook|supersaas|booksy|fresha|treatwell|"
                              r"rezervace online|online rezervac\w*|objednat online|rezervovat)", re.I)
ESHOP_PATTERNS = re.compile(r"(do košíku|přidat do košíku|add to cart|košík\b|nákupní košík|eshop|e-shop)", re.I)
BUILDER_CMS = {"Wix", "Webnode", "Squarespace", "Eshop-rychle"}


@dataclass
class PageData:
    kind: str
    url: str
    final_url: str
    status_code: int
    html: str
    elapsed_ms: int
    size_bytes: int


@dataclass
class CrawlResult:
    url: str
    final_url: str | None = None
    reachable: bool = False
    robots_allowed: bool | None = None
    status_code: int | None = None
    error: str | None = None
    pages: dict[str, PageData] = field(default_factory=dict)
    discovered: dict[str, str] = field(default_factory=dict)
    extracted: dict[str, Any] = field(default_factory=dict)


def visible_text(soup: BeautifulSoup) -> str:
    for t in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _same_site(url: str, base_host: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return registered_domain(host) == registered_domain(base_host)


def discover_pages(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    base_host = urlparse(base_url).hostname or ""
    found: dict[str, tuple[int, str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        if not url.startswith("http") or not _same_site(url, base_host):
            continue
        if re.search(r"\.(pdf|jpe?g|png|gif|webp|zip|docx?|xlsx?|mp4)$", url, re.I):
            continue
        path = urlparse(url).path.lower()
        label = (a.get_text(" ", strip=True) or "").lower()[:80]
        hay = f"{path} {label}"
        for kind, pat in PAGE_PATTERNS.items():
            if pat.search(hay):
                # kratší cesta = pravděpodobněji hlavní stránka sekce
                score = len(path) + (0 if pat.search(label) else 20)
                if kind not in found or score < found[kind][0]:
                    found[kind] = (score, url)
    # stejná URL nemá být použita pro více typů
    out: dict[str, str] = {}
    used: set[str] = set()
    for kind in PAGE_FETCH_ORDER:
        if kind in found and found[kind][1] not in used and found[kind][1].rstrip("/") != base_url.rstrip("/"):
            out[kind] = found[kind][1]
            used.add(found[kind][1])
    return out


def _parse_prices(text: str) -> list[float]:
    out = []
    for m in PRICE_RE.finditer(text):
        num = re.sub(r"[  .]", "", m.group(1))
        try:
            v = float(num)
        except ValueError:
            continue
        if m.group(2).upper() in ("€", "EUR"):
            v *= 25  # orientační přepočet
        if 50 <= v <= 5_000_000:
            out.append(v)
    return out


def extract_page(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    raw_html = html
    head_info: dict[str, Any] = {}
    title = soup.title.get_text(strip=True) if soup.title else None
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    og_img = soup.find("meta", attrs={"property": "og:image"})
    html_tag = soup.find("html")
    head_info.update(
        title=title,
        meta_description=md.get("content") if md else None,
        generator=gen.get("content") if gen else None,
        has_viewport=bool(vp and "width" in (vp.get("content") or "")),
        has_og_image=bool(og_img),
        has_favicon=bool(soup.find("link", rel=re.compile("icon", re.I))),
        lang=html_tag.get("lang") if html_tag else None,
    )
    # strukturovaná data
    ld_types = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if isinstance(it, dict) and it.get("@type"):
                ld_types.append(str(it.get("@type")))
    links_social: dict[str, str] = {}
    emails: set[str] = set()
    phones: set[str] = set()
    lang_links = False
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            e = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.fullmatch(e):
                emails.add(e)
        elif href.startswith("tel:"):
            p = normalize_phone(href[4:])
            if p:
                phones.add(p)
        else:
            plat = social_platform(href)
            if plat and plat not in links_social and not re.search(r"/(sharer|share|intent|dialog)", href):
                links_social[plat] = href.split("?")[0]
            txt = a.get_text(strip=True).lower()
            if txt in ("en", "english", "de", "deutsch") or re.search(r"/(en|de)(/|$)", urlparse(urljoin(url, href)).path):
                lang_links = True
    imgs = soup.find_all("img")
    img_no_alt = sum(1 for i in imgs if not (i.get("alt") or "").strip())
    deprecated = sum(len(soup.find_all(t)) for t in ("font", "center", "marquee", "frameset", "frame", "blink"))
    tables = soup.find_all("table")
    layout_tables = sum(1 for t in tables if t.find("table") or (not t.find("th") and len(t.find_all("td")) > 12))
    inline_styles = len(soup.find_all(style=True))
    h1 = [h.get_text(" ", strip=True)[:200] for h in soup.find_all("h1")]
    h2 = [h.get_text(" ", strip=True)[:200] for h in soup.find_all("h2")][:15]
    forms = soup.find_all("form")
    has_contact_form = any(f.find("textarea") for f in forms)
    iframe_src = " ".join(i.get("src", "") for i in soup.find_all("iframe"))
    has_map = "google.com/maps" in iframe_src or "mapy.cz" in iframe_src or "mapy.com" in iframe_src
    has_video = bool(soup.find("video")) or "youtube.com/embed" in iframe_src or "vimeo" in iframe_src
    text = visible_text(soup)
    for e in EMAIL_RE.findall(text):
        if not re.search(r"\.(png|jpg|webp|gif)$", e, re.I):
            emails.add(e.lower())
    for m in PHONE_RE.findall(text):
        p = normalize_phone(m)
        if p:
            phones.add(p)
    icos = set()
    for m in ICO_RE.findall(text):
        d = re.sub(r"\D", "", m).zfill(8)
        if is_valid_ico(d):
            icos.add(d)
    tech = sorted({name for name, pat in TECH_PATTERNS.items() if pat.search(raw_html)})
    jq = re.search(r"jquery[.-](\d+)\.(\d+)", raw_html, re.I)
    bs = re.search(r"bootstrap[@/-]?(\d)\.\d", raw_html, re.I)
    years = []
    for m in COPYRIGHT_RE.finditer(text):
        years.extend(int(y) for y in m.groups() if y)
    persons = []
    for m in PERSON_ROLE_RE.finditer(text):
        persons.append({"role": m.group(1), "name": m.group(2).strip()})
    for m in PERSON_ROLE_REV_RE.finditer(text):
        persons.append({"role": m.group(2), "name": m.group(1).strip()})
    dates = []
    for d, mth, y in DATE_RE.findall(text):
        try:
            dates.append(date(int(y), int(mth), int(d)).isoformat())
        except ValueError:
            pass
    since = [int(y) for y in SINCE_RE.findall(text)]
    years_exp = [int(y) for y in YEARS_EXP_RE.findall(text) if 0 < int(y) < 80]

    def snippets(pat: re.Pattern, limit: int = 3) -> list[str]:
        """Úryvky kolem shod; preferuje obsah před navigací (začátek stránky)."""
        matches = list(pat.finditer(text))
        body = [m for m in matches if m.start() > 400] or matches
        out = []
        for m in body:
            s = max(0, m.start() - 70)
            out.append(text[s:m.end() + 90].strip())
            if len(out) >= limit:
                break
        return out

    return {
        **head_info,
        "ld_types": ld_types[:10],
        "socials": links_social,
        "emails": sorted(emails)[:10],
        "phones": sorted(phones)[:10],
        "icos": sorted(icos),
        "image_count": len(imgs),
        "images_without_alt": img_no_alt,
        "deprecated_tags": deprecated,
        "layout_tables": layout_tables,
        "inline_styles": inline_styles,
        "h1": h1[:5],
        "h2": h2,
        "forms": len(forms),
        "has_contact_form": has_contact_form,
        "has_map": has_map,
        "has_video": has_video,
        "has_language_switch": lang_links,
        "technologies": tech,
        "jquery_version": f"{jq.group(1)}.{jq.group(2)}" if jq else None,
        "bootstrap_major": int(bs.group(1)) if bs else None,
        "copyright_years": sorted(set(years)),
        "persons": persons[:10],
        "dates": sorted(set(dates))[-20:],
        "since_years": since[:5],
        "years_experience": years_exp[:5],
        "prices": _parse_prices(text)[:200],
        "has_booking": bool(BOOKING_PATTERNS.search(raw_html) or BOOKING_PATTERNS.search(text)),
        "has_eshop": bool(ESHOP_PATTERNS.search(text)) or any(t in tech for t in ("WooCommerce", "Shoptet", "Shopify", "Upgates", "PrestaShop", "Eshop-rychle")),
        "text_signals": {k: snippets(p) for k, p in TEXT_SIGNALS.items() if p.search(text)},
        "quality": {k: len(p.findall(text)) for k, p in QUALITY_PATTERNS.items()},
        "quality_snippets": {k: snippets(p, 2) for k, p in QUALITY_PATTERNS.items() if k in ("testimonials", "awards", "press", "premium") and p.search(text)},
        "word_count": len(text.split()),
        "text": text[:20000],
    }


def merge_extracted(pages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Sloučí extrakce ze všech stránek do jednoho profilu webu."""
    home = pages.get("home", {})
    agg: dict[str, Any] = {k: home.get(k) for k in (
        "title", "meta_description", "generator", "has_viewport", "has_og_image", "has_favicon", "lang", "h1", "h2",
        "jquery_version", "bootstrap_major", "image_count", "images_without_alt", "deprecated_tags", "layout_tables",
        "inline_styles", "word_count")}
    socials: dict[str, str] = {}
    emails: set[str] = set()
    phones: set[str] = set()
    icos: set[str] = set()
    tech: set[str] = set()
    years: set[int] = set()
    persons: list[dict] = []
    dates: set[str] = set()
    prices: list[float] = []
    text_signals: dict[str, list[dict]] = {}
    quality: dict[str, int] = {}
    quality_snips: dict[str, list[str]] = {}
    since: list[int] = []
    years_exp: list[int] = []
    flags = {"has_booking": False, "has_eshop": False, "has_contact_form": False, "has_map": False,
             "has_video": False, "has_language_switch": False}
    ld_types: set[str] = set()
    for kind, p in pages.items():
        socials.update({k: v for k, v in (p.get("socials") or {}).items() if k not in socials})
        emails.update(p.get("emails") or [])
        phones.update(p.get("phones") or [])
        icos.update(p.get("icos") or [])
        tech.update(p.get("technologies") or [])
        years.update(p.get("copyright_years") or [])
        ld_types.update(p.get("ld_types") or [])
        for per in p.get("persons") or []:
            if not any(x["name"] == per["name"] for x in persons):
                persons.append({**per, "page": kind})
        dates.update(p.get("dates") or [])
        prices.extend(p.get("prices") or [])
        since.extend(p.get("since_years") or [])
        years_exp.extend(p.get("years_experience") or [])
        for k, snips in (p.get("text_signals") or {}).items():
            text_signals.setdefault(k, [])
            for s in snips:
                if len(text_signals[k]) < 3:
                    text_signals[k].append({"snippet": s, "page": kind, "url": p.get("_url")})
        for k, v in (p.get("quality") or {}).items():
            quality[k] = quality.get(k, 0) + v
        for k, snips in (p.get("quality_snippets") or {}).items():
            quality_snips.setdefault(k, [])
            quality_snips[k].extend(snips[: 2 - len(quality_snips[k])])
        for f in flags:
            flags[f] = flags[f] or bool(p.get(f))
    portfolio = pages.get("portfolio", {})
    today = date.today().isoformat()
    valid_dates = sorted(d for d in dates if d <= today)
    cms = None
    gen = (home.get("generator") or "").lower()
    for name in ("WordPress", "Wix", "Webnode", "Shoptet", "Squarespace", "Webflow", "Joomla", "Drupal", "Shopify",
                 "Upgates", "PrestaShop", "Eshop-rychle", "Next.js"):
        if name.lower() in gen or name in tech:
            cms = name
            break
    agg.update(
        ld_types=sorted(ld_types),
        socials=socials,
        emails=sorted(e for e in emails if not e.endswith(("example.com", "sentry.io", "wixpress.com")))[:10],
        phones=sorted(phones)[:6],
        icos=sorted(icos),
        technologies=sorted(tech),
        cms=cms,
        uses_site_builder=cms in BUILDER_CMS,
        copyright_year=max(years) if years else None,
        persons=persons[:10],
        latest_date=valid_dates[-1] if valid_dates else None,
        price_count=len(prices),
        price_median=statistics.median(prices) if prices else None,
        price_max=max(prices) if prices else None,
        since_year=min(since) if since else None,
        years_experience=max(years_exp) if years_exp else None,
        text_signals=text_signals,
        quality=quality,
        quality_snippets=quality_snips,
        portfolio_image_count=portfolio.get("image_count"),
        pages_crawled=sorted(pages.keys()),
        total_word_count=sum(p.get("word_count") or 0 for p in pages.values()),
        **flags,
    )
    return agg


def crawl_site(url: str, fetcher: PoliteFetcher | None = None, max_subpages: int | None = None) -> CrawlResult:
    s = get_settings()
    max_subpages = s.max_pages_per_site if max_subpages is None else max_subpages
    own = fetcher is None
    fetcher = fetcher or PoliteFetcher()
    res = CrawlResult(url=url)
    try:
        try:
            res.robots_allowed = fetcher.robots_allowed(url)
            home = fetcher.get(url)
        except BlockedByPolicy as exc:
            res.error = str(exc)
            res.robots_allowed = False if "robots" in str(exc) else res.robots_allowed
            return res
        except Exception as exc:  # noqa: BLE001
            res.error = f"{type(exc).__name__}: {exc}"[:500]
            return res
        res.status_code = home.status_code
        res.final_url = home.final_url
        if home.status_code >= 400:
            res.error = f"HTTP {home.status_code}"
            return res
        ctype = home.headers.get("content-type", "")
        if "html" not in ctype and "<html" not in home.text[:2000].lower():
            res.error = f"Neočekávaný typ obsahu: {ctype}"
            return res
        res.reachable = True
        res.pages["home"] = PageData("home", url, home.final_url, home.status_code, home.text, home.elapsed_ms, len(home.content))
        soup = BeautifulSoup(home.text, "lxml")
        res.discovered = discover_pages(soup, home.final_url)
        extracted_pages: dict[str, dict[str, Any]] = {"home": {**extract_page(home.text, home.final_url), "_url": home.final_url}}
        for kind in PAGE_FETCH_ORDER:
            if len(res.pages) > max_subpages:
                break
            sub = res.discovered.get(kind)
            if not sub:
                continue
            try:
                r = fetcher.get(sub, attempts=2)
            except (BlockedByPolicy, FetchError) as exc:
                log.info("Podstránka %s přeskočena: %s", sub, exc)
                continue
            except Exception as exc:  # noqa: BLE001
                log.info("Podstránka %s selhala: %s", sub, exc)
                continue
            if r.status_code >= 400:
                continue
            res.pages[kind] = PageData(kind, sub, r.final_url, r.status_code, r.text, r.elapsed_ms, len(r.content))
            extracted_pages[kind] = {**extract_page(r.text, r.final_url), "_url": r.final_url}
        res.extracted = merge_extracted(extracted_pages)
        res.extracted["home_response_ms"] = home.elapsed_ms
        res.extracted["home_size_kb"] = round(len(home.content) / 1024, 1)
        res.extracted["https"] = home.final_url.startswith("https://")
        res.extracted["redirected_to_https"] = url.startswith("http://") and home.final_url.startswith("https://")
        res.extracted["text_excerpt"] = (extracted_pages["home"].get("text") or "")[:3000]
        res.extracted["page_texts"] = {k: (v.get("text") or "")[:4000] for k, v in extracted_pages.items()}
        return res
    finally:
        if own:
            fetcher.close()
