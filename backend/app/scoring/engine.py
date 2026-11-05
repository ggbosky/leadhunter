"""Transparentní scoring leadů.

Komponenty (každá zvlášť, s důvody a mírou jistoty):
- Design Gap (30 %): rozdíl mezi kvalitou podnikání a kvalitou webu
- Commercial Potential (25 %): odhad ekonomické atraktivity
- Buying Readiness (20 %): síla aktuálních signálů možné investice
- Service Fit (15 %): soulad s nabídkou Project Two
- Contactability (10 %): dosažitelnost rozhodovací osoby

Neznámé hodnoty = None (nikdy 0). Opportunity Score se přepočítá jen ze známých
komponent a pokud je známých málo, není vypočten vůbec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..segments import SERVICES, get_segment

ALGORITHM_VERSION = "1.0"

CATEGORY_LABELS = {
    "priority": "Priority Lead",
    "strong": "Strong Opportunity",
    "potential": "Potential Lead",
    "low": "Low Priority",
    "insufficient": "Nedostatek dat",
}

DISQUALIFICATION_LABELS = {
    "insufficient_activity": "Nedostatečná obchodní aktivita",
    "low_commercial": "Velmi nízký ekonomický potenciál",
    "good_website": "Již kvalitní web",
    "insufficient_data": "Nedostatek ověřitelných dat",
    "unsuitable_segment": "Nevhodný segment",
    "duplicate": "Duplicita",
    "already_contacted": "Firma již byla oslovena",
    "do_not_contact": "Firma odmítla kontaktování",
}
HARD_DISQUALIFIERS = {"do_not_contact", "good_website", "unsuitable_segment", "duplicate", "insufficient_activity"}

DECISION_ROLES = ("founder", "co-founder", "zakladatel", "spoluzakladatel", "owner", "majitel", "ceo", "managing director",
                  "jednatel", "ředitel", "marketing", "e-commerce", "ecommerce", "společník", "předseda", "provozovatel")


@dataclass
class Factor:
    label: str
    value: float | None  # 0–100, None = neznámé
    weight: float
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": None if self.value is None else round(self.value, 1),
                "weight": self.weight, "evidence": self.evidence, "known": self.value is not None}


@dataclass
class Component:
    key: str
    label: str
    score: float | None
    confidence: float
    reasons: list[str] = field(default_factory=list)
    factors: list[Factor] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "score": None if self.score is None else round(self.score, 1),
                "confidence": round(self.confidence, 2), "reasons": self.reasons,
                "factors": [f.to_dict() for f in self.factors], "note": self.note}


@dataclass
class LeadContext:
    company_name: str
    segment_key: str | None
    country: str = "CZ"
    has_website: bool = False
    website_reachable: bool | None = None
    extracted: dict[str, Any] = field(default_factory=dict)
    technical_score: float | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)
    visual: dict[str, Any] | None = None  # {status, visual_score, confidence, criteria, business_quality_score}
    signals: list[dict[str, Any]] = field(default_factory=list)  # {signal_type, strength, description, evidence, age_factor}
    contacts: list[dict[str, Any]] = field(default_factory=list)  # {name, role, linkedin_url, email, phone, is_decision_maker}
    company_email: str | None = None
    company_phone: str | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    legal_form: str | None = None
    founded_on: str | None = None
    registry_active: bool | None = None
    capital_czk: int | None = None
    suppressed: bool = False
    already_contacted: bool = False
    segment_enabled: bool = True
    segment_multiplier: float = 1.0
    settings_scoring: dict[str, Any] = field(default_factory=dict)
    pricing: dict[str, Any] = field(default_factory=dict)


def _wmean(factors: list[Factor]) -> tuple[float | None, float]:
    total_w = sum(f.weight for f in factors)
    known = [f for f in factors if f.value is not None]
    kw = sum(f.weight for f in known)
    if not known or kw == 0:
        return None, 0.0
    return sum(f.value * f.weight for f in known) / kw, (kw / total_w if total_w else 0.0)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _criterion(visual: dict | None, key: str) -> float | None:
    if not visual or visual.get("status") != "complete":
        return None
    for c in visual.get("criteria") or []:
        if c.get("key") == key:
            return c.get("score")
    return None


def years_in_business(ctx: LeadContext) -> tuple[float | None, str]:
    ex = ctx.extracted
    candidates: list[tuple[float, str]] = []
    if ctx.founded_on:
        try:
            fd = date.fromisoformat(ctx.founded_on[:10])
            candidates.append(((date.today() - fd).days / 365.25, f"vznik dle ARES {fd.year}"))
        except ValueError:
            pass
    if ex.get("since_year"):
        candidates.append((date.today().year - ex["since_year"], f"na webu uvedeno 'od roku {ex['since_year']}'"))
    if ex.get("years_experience"):
        candidates.append((float(ex["years_experience"]), f"na webu uvedeno {ex['years_experience']} let zkušeností"))
    if not candidates:
        return None, ""
    yrs, ev = max(candidates, key=lambda x: x[0])
    return yrs, ev


# ---------------------------------------------------------------------------
# Business quality & website quality
# ---------------------------------------------------------------------------
def business_quality(ctx: LeadContext) -> Component:
    ex = ctx.extracted
    crawled = bool(ex)
    factors: list[Factor] = []
    reasons: list[str] = []

    # AI dojem z obsahu (fotky práce, prezentace služeb)
    bq_ai = (ctx.visual or {}).get("business_quality_score") if (ctx.visual or {}).get("status") == "complete" else None
    factors.append(Factor("AI dojem z obsahu a fotek práce (expertní odhad)", bq_ai, 2.0,
                          (ctx.visual or {}).get("business_impression") or ""))
    photo = _criterion(ctx.visual, "photography")
    factors.append(Factor("Kvalita fotografií (vision model)", photo, 1.5, "kritérium 'Kvalita fotografií'" if photo is not None else ""))

    # portfolio
    pv = None
    pev = ""
    if crawled:
        if "portfolio" in (ex.get("pages_crawled") or []):
            n = ex.get("portfolio_image_count") or 0
            pv = 85 if n >= 20 else 72 if n >= 8 else 55 if n >= 1 else 40
            pev = f"stránka portfolia/realizací s {n} obrázky"
    factors.append(Factor("Veřejné portfolio / realizace", pv, 1.5, pev))

    # sociální sítě (pouze odkazy, aktivitu neověřujeme scrapingem)
    socials = {**(ctx.social_links or {}), **(ex.get("socials") or {})}
    vis_platforms = [p for p in socials if p in ("instagram", "facebook", "pinterest", "youtube", "tiktok", "houzz", "behance", "vimeo")]
    sv = None
    if crawled or socials:
        n = len(vis_platforms)
        sv = 30 if n == 0 else 55 if n == 1 else 70 if n == 2 else 82
    factors.append(Factor("Přítomnost značky na sociálních sítích", sv, 0.8,
                          (", ".join(vis_platforms) + " (aktivita neověřena)") if vis_platforms else "žádné odkazy"))

    # reference, ocenění, média
    q = ex.get("quality") or {}
    rv = None
    rev = []
    if crawled:
        rv = 40
        if q.get("testimonials"):
            rv += 25
            rev.append("reference/recenze klientů")
        if q.get("awards"):
            rv += 15
            rev.append("ocenění")
        if q.get("press"):
            rv += 12
            rev.append("zmínky v médiích")
    factors.append(Factor("Reference, recenze, ocenění", None if rv is None else _clamp(rv), 1.2, ", ".join(rev) or "nenalezeno"))

    # rozsah a prezentace nabídky
    ov = None
    if crawled:
        wc = ex.get("total_word_count") or 0
        has_services = "services" in (ex.get("pages_crawled") or [])
        ov = 35 + (20 if has_services else 0) + min(30, wc / 100) + (10 if ex.get("price_count") else 0)
    factors.append(Factor("Rozsah a popis nabídky", None if ov is None else _clamp(ov), 1.0,
                          f"{ex.get('total_word_count', 0)} slov textu, {'stránka služeb' if 'services' in (ex.get('pages_crawled') or []) else 'bez stránky služeb'}" if crawled else ""))

    # prémiové pozicování
    prem = q.get("premium")
    pmv = None if not crawled else (40 if not prem else 58 if prem <= 2 else 72 if prem <= 6 else 85)
    factors.append(Factor("Prémiové pozicování (jazyk nabídky)", pmv, 0.8, f"{prem or 0}× výrazy typu 'na míru', 'prémiový'…"))

    # stáří firmy
    yrs, yev = years_in_business(ctx)
    yv = None if yrs is None else (82 if yrs >= 10 else 70 if yrs >= 5 else 56 if yrs >= 2 else 45)
    factors.append(Factor("Délka působení na trhu", yv, 0.8, yev))

    score, coverage = _wmean(factors)
    known_strong = sum(1 for f in factors if f.value is not None)
    if score is None or coverage < 0.35 or known_strong < 3:
        return Component("business_quality", "Kvalita podnikání", None, coverage, ["Nedostatek dat o kvalitě podnikání"], factors,
                         note="Bez dostatečných dat nevypočítáváme falešně přesné skóre.")
    top = sorted([f for f in factors if f.value is not None], key=lambda f: -f.value * f.weight)[:3]
    reasons = [f"{f.label}: {f.evidence}" for f in top if f.evidence]
    return Component("business_quality", "Kvalita podnikání", score, coverage, reasons, factors)


def website_quality(ctx: LeadContext) -> tuple[float | None, float, str, list[str]]:
    """Vrací (skóre, jistota, základ, důvody). Základ: visual | technical | no_website | none."""
    if not ctx.has_website:
        return 0.0, 0.85, "no_website", ["Firma nemá vlastní web"]
    if ctx.website_reachable is False:
        return 5.0, 0.6, "technical", ["Web není dostupný"]
    v = ctx.visual or {}
    if v.get("status") == "complete" and v.get("visual_score") is not None:
        vs = float(v["visual_score"])
        if ctx.technical_score is not None:
            score = 0.8 * vs + 0.2 * ctx.technical_score
        else:
            score = vs
        reasons = [f"Website Visual Score {vs:.0f}/100 (expertní odhad AI)"]
        if ctx.technical_score is not None:
            reasons.append(f"Technické skóre {ctx.technical_score:.0f}/100")
        return score, max(0.3, float(v.get("confidence") or 0.5)), "visual", reasons
    if ctx.technical_score is not None:
        return ctx.technical_score, 0.3, "technical", [
            f"Pouze technické skóre {ctx.technical_score:.0f}/100 – vizuální analýza neproběhla (audit neúplný)"]
    return None, 0.0, "none", ["Web zatím nebyl analyzován"]


def design_gap(ctx: LeadContext, bq: Component) -> tuple[Component, float | None, str]:
    wq, wq_conf, basis, wq_reasons = website_quality(ctx)
    factors = [Factor("Kvalita podnikání", bq.score, 1.0), Factor("Kvalita webu", wq, 1.0, basis)]
    if bq.score is None or wq is None:
        reason = "Nedostatek dat o kvalitě podnikání" if bq.score is None else "Web zatím nebyl analyzován"
        return Component("design_gap", "Design Gap", None, 0.0, [reason] + wq_reasons, factors,
                         note="Skóre se nepočítá, dokud nejsou k dispozici obě strany porovnání."), wq, basis
    gap = _clamp((100 - wq) * bq.score / 100 * 1.25)
    conf = min(bq.confidence, wq_conf)
    if basis == "technical":
        conf *= 0.6
    reasons = [f"Kvalita podnikání {bq.score:.0f}/100 vs. kvalita webu {wq:.0f}/100"] + wq_reasons + bq.reasons[:2]
    if basis == "no_website":
        reasons.append("Bez webu: příležitost pro nový web, pokud je podnikání kvalitní")
    return Component("design_gap", "Design Gap", gap, conf, reasons, factors,
                     note="Vzorec: (100 − kvalita webu) × kvalita podnikání / 100 × 1,25"), wq, basis


# ---------------------------------------------------------------------------
def commercial_potential(ctx: LeadContext) -> Component:
    seg = get_segment(ctx.segment_key)
    ex = ctx.extracted
    crawled = bool(ex)
    q = ex.get("quality") or {}
    factors: list[Factor] = []
    factors.append(Factor("Typická hodnota služeb v oboru", seg.economic_base if seg else None, 1.5, seg.label if seg else "obor neurčen"))
    pm = ex.get("price_median")
    pv = None
    pev = ""
    if pm:
        pv = 85 if pm >= 10000 else 75 if pm >= 3000 else 60 if pm >= 1000 else 45 if pm >= 400 else 32
        pev = f"medián cen na webu {int(pm):,} Kč ({ex.get('price_count')} cen)".replace(",", " ")
    factors.append(Factor("Cenová hladina (ceny uvedené na webu)", pv, 1.2, pev))
    lf = (ctx.legal_form or "").lower()
    lv = None
    if lf:
        lv = 80 if "akciov" in lf else 66 if "ručením" in lf or "s.r.o" in lf else 45 if "fyzická" in lf or "osvč" in lf else 55
    factors.append(Factor("Právní forma", lv, 0.7, ctx.legal_form or ""))
    cv = None
    if ctx.capital_czk is not None:
        cv = 82 if ctx.capital_czk >= 1_000_000 else 66 if ctx.capital_czk >= 200_000 else 50
    factors.append(Factor("Základní kapitál (obchodní rejstřík)", cv, 0.4,
                          f"{ctx.capital_czk:,} Kč".replace(",", " ") if ctx.capital_czk is not None else ""))
    br = q.get("branches")
    factors.append(Factor("Více provozoven / showroom", (75 if br and br >= 3 else 60 if br else 45) if crawled else None, 0.6,
                          f"{br or 0}× zmínka o pobočce/provozovně/showroomu"))
    tm = q.get("team")
    factors.append(Factor("Tým / zaměstnanci", (66 if tm else 48) if crawled else None, 0.5, "zmínka o týmu" if tm else "bez zmínky o týmu"))
    prem = q.get("premium")
    factors.append(Factor("Prémiový segment", (40 if not prem else 60 if prem <= 2 else 75 if prem <= 6 else 85) if crawled else None, 1.0,
                          f"{prem or 0}× prémiové výrazy"))
    mk = [t for t in (ex.get("technologies") or []) if t in ("Meta Pixel", "Seznam Sklik", "Google Tag Manager", "Google Analytics", "Hotjar")]
    factors.append(Factor("Investice do marketingu", (72 if len(mk) >= 2 else 60 if mk else 42) if crawled else None, 0.6,
                          ", ".join(mk) or "žádné marketingové nástroje"))
    hv = (q.get("weddings") or 0) + (q.get("b2b") or 0)
    factors.append(Factor("Zakázky s vyšší hodnotou (svatby, B2B)", (72 if hv >= 3 else 60 if hv else 45) if crawled else None, 0.5,
                          f"{hv}× zmínka"))
    yrs, yev = years_in_business(ctx)
    factors.append(Factor("Stabilita (délka působení)", None if yrs is None else (75 if yrs >= 8 else 62 if yrs >= 3 else 48), 0.6, yev))
    intl = ctx.country not in ("CZ", "SK") or ex.get("has_language_switch")
    factors.append(Factor("Zahraniční klientela / jazykové verze", (75 if intl else 50) if crawled or ctx.country not in ("CZ", "SK") else None,
                          0.5, "jazykové verze webu" if ex.get("has_language_switch") else ("zahraniční trh" if intl else "pouze čeština")))
    score, coverage = _wmean(factors)
    if score is None:
        return Component("commercial_potential", "Commercial Potential", None, 0.0, ["Nedostatek dat"], factors)
    top = sorted([f for f in factors if f.value is not None and f.evidence], key=lambda f: -abs(f.value - 50) * f.weight)[:4]
    reasons = [f"{f.label}: {f.evidence}" for f in top]
    return Component("commercial_potential", "Commercial Potential", score, coverage * 0.9, reasons, factors,
                     note="Odhad ekonomické atraktivity – nejde o potvrzený rozpočet.")


def buying_readiness(ctx: LeadContext) -> Component:
    if not ctx.extracted and not ctx.signals and ctx.founded_on is None:
        return Component("buying_readiness", "Buying Readiness", None, 0.0, ["Signály zatím nebyly vyhodnoceny (web neanalyzován)"])
    if not ctx.signals:
        return Component("buying_readiness", "Buying Readiness", 10.0, 0.4,
                         ["Nenalezeny žádné aktuální signály investice (nábor, pobočky, nové služby…)"],
                         note="Nízká hodnota = signály nebyly nalezeny, ne potvrzení nezájmu.")
    p_none = 1.0
    by_type: dict[str, float] = {}
    for s in ctx.signals:
        st = float(s.get("strength") or 0.3) * float(s.get("age_factor") or 1.0)
        by_type[s["signal_type"]] = max(by_type.get(s["signal_type"], 0.0), st)
    for st in by_type.values():
        p_none *= (1 - min(0.9, st))
    score = (1 - p_none) * 100
    reasons = [f"{s.get('description')}: {(s.get('evidence') or '')[:140]}" for s in
               sorted(ctx.signals, key=lambda x: -float(x.get("strength") or 0))[:4]]
    conf = min(0.85, 0.45 + 0.1 * len(by_type))
    return Component("buying_readiness", "Buying Readiness", _clamp(score), conf, reasons,
                     [Factor(t, v * 100, 1.0) for t, v in by_type.items()])


def service_fit(ctx: LeadContext, wq: float | None, basis: str) -> tuple[Component, str | None]:
    seg = get_segment(ctx.segment_key)
    reasons: list[str] = []
    if not ctx.segment_enabled:
        return Component("service_fit", "Service Fit", 15.0, 0.9, ["Segment je v nastavení vypnutý"]), None
    if seg:
        base = {1: 85, 2: 72, 3: 55}[seg.tier]
        reasons.append(f"{seg.label} (Tier {seg.tier})")
        base += (seg.visual_importance - 70) / 3
        if ctx.segment_multiplier != 1.0:
            reasons.append(f"Priorita segmentu ×{ctx.segment_multiplier:.2f} (dle nastavení/výsledků)")
        base *= ctx.segment_multiplier
        conf = 0.8
    else:
        base = 45
        conf = 0.4
        reasons.append("Obor se nepodařilo určit")
    ex = ctx.extracted
    service = seg.typical_service if seg else "full_web"
    brand = _criterion(ctx.visual, "brand_consistency")
    if basis == "no_website":
        service = "new_web"
        reasons.append("Firma nemá web → nabídka nového webu")
    elif ex.get("has_eshop"):
        service = "eshop"
        reasons.append("Web obsahuje e-shop → redesign e-shopu")
    elif brand is not None and brand < 40:
        service = "rebranding_web"
        base += 5
        reasons.append(f"Slabá konzistence brandingu ({brand:.0f}/100) → rebranding + web")
    elif wq is not None and wq < 35:
        base += 5
        reasons.append("Výrazně zastaralý web → kompletní redesign")
    return Component("service_fit", "Service Fit", _clamp(base), conf, reasons), service


def contactability(ctx: LeadContext) -> Component:
    score = 0.0
    reasons = []
    dm = [c for c in ctx.contacts if c.get("name") and (c.get("is_decision_maker") or any(r in (c.get("role") or "").lower() for r in DECISION_ROLES))]
    if dm:
        score += 45
        reasons.append(f"Rozhodovací osoba: {dm[0]['name']} ({dm[0].get('role') or 'role neuvedena'})")
    elif ctx.contacts:
        score += 20
        reasons.append("Kontakt uložen, role rozhodovací osoby neověřena")
    if any(c.get("linkedin_url") for c in ctx.contacts):
        score += 25
        reasons.append("LinkedIn profil uložen")
    if ctx.company_email or any(c.get("email") for c in ctx.contacts) or (ctx.extracted.get("emails")):
        score += 15
        reasons.append("E-mail k dispozici")
    if ctx.company_phone or ctx.extracted.get("phones"):
        score += 8
        reasons.append("Telefon k dispozici")
    if ctx.extracted.get("has_contact_form") or ctx.extracted.get("has_booking"):
        score += 4
    if ctx.social_links or ctx.extracted.get("socials"):
        score += 3
    if not reasons:
        reasons.append("Zatím žádný ověřený kontakt")
    return Component("contactability", "Contactability", _clamp(score), 0.9, reasons)


# ---------------------------------------------------------------------------
def category_for(score: float | None) -> str:
    if score is None:
        return "insufficient"
    if score >= 80:
        return "priority"
    if score >= 60:
        return "strong"
    if score >= 40:
        return "potential"
    return "low"


def estimated_budget(service: str | None, pricing: dict[str, Any]) -> dict[str, Any] | None:
    if not service:
        return None
    if not pricing:
        from ..settings_store import DEFAULTS

        pricing = DEFAULTS["pricing"]
    p = pricing.get(service)
    if not p:
        return None
    return {"service": service, "label": p.get("label") or SERVICES.get(service), "min": p.get("min"), "max": p.get("max"),
            "note": "Orientační cenové pásmo Project Two – nejde o zjištěný rozpočet klienta."}


def outreach_reason(ctx: LeadContext, comps: dict[str, Component], wq: float | None, basis: str) -> str:
    parts = []
    bq = comps["business_quality"]
    if bq.score is not None and bq.score >= 60:
        good = [f.evidence for f in sorted(bq.factors, key=lambda f: -(f.value or 0) * f.weight) if f.value and f.value >= 60 and f.evidence][:2]
        if good:
            parts.append("Silná stránka podnikání: " + "; ".join(good))
    if basis == "no_website":
        parts.append("firma nemá vlastní web")
    elif wq is not None:
        top_issues = [i["title"] for i in ctx.issues[:2]]
        vis = ctx.visual or {}
        if vis.get("status") == "complete" and vis.get("top_issues"):
            top_issues = vis["top_issues"][:2]
        if wq < 55:
            parts.append(f"web zaostává (kvalita {wq:.0f}/100): " + "; ".join(top_issues))
    sig = comps["buying_readiness"]
    if sig.score and sig.score > 30:
        parts.append("aktuální signál: " + sig.reasons[0][:120])
    return ". ".join(p[0].upper() + p[1:] for p in parts if p) or "Zatím bez jasného důvodu oslovení."


def score_lead(ctx: LeadContext) -> dict[str, Any]:
    weights = (ctx.settings_scoring or {}).get("weights") or {
        "design_gap": 0.30, "commercial_potential": 0.25, "buying_readiness": 0.20, "service_fit": 0.15, "contactability": 0.10}
    min_known = float((ctx.settings_scoring or {}).get("min_known_weight", 0.55))
    good_visual = float((ctx.settings_scoring or {}).get("already_good_visual_score", 80))
    low_comm = float((ctx.settings_scoring or {}).get("low_commercial_threshold", 25))

    bq = business_quality(ctx)
    dg, wq, basis = design_gap(ctx, bq)
    cp = commercial_potential(ctx)
    br = buying_readiness(ctx)
    sf, service = service_fit(ctx, wq, basis)
    ct = contactability(ctx)
    comps = {"business_quality": bq, "design_gap": dg, "commercial_potential": cp, "buying_readiness": br,
             "service_fit": sf, "contactability": ct}

    total_w = sum(weights.values())
    known = {k: comps[k] for k in weights if comps[k].score is not None}
    known_w = sum(weights[k] for k in known) / total_w if total_w else 0
    if known and known_w >= min_known:
        opp = sum(comps[k].score * weights[k] for k in known) / sum(weights[k] for k in known)
    else:
        opp = None
    confidence = sum(weights[k] * comps[k].confidence for k in known) / total_w * 100 if total_w else 0

    # důvody vyřazení
    dq: list[dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        dq.append({"code": code, "label": DISQUALIFICATION_LABELS[code], "detail": detail})

    if ctx.suppressed:
        add("do_not_contact", "Firma je na seznamu Do Not Contact")
    if ctx.already_contacted:
        add("already_contacted", "Firma už byla oslovena – další oslovení jen přes follow-up")
    v = ctx.visual or {}
    if v.get("status") == "complete" and v.get("visual_score") is not None and v["visual_score"] >= good_visual:
        add("good_website", f"Website Visual Score {v['visual_score']:.0f}/100")
    if cp.score is not None and cp.score < low_comm and cp.confidence >= 0.5:
        add("low_commercial", f"Commercial Potential {cp.score:.0f}/100")
    if ctx.registry_active is False:
        add("insufficient_activity", "Subjekt není podle ARES aktivní")
    elif ctx.has_website and ctx.website_reachable is False and not ctx.social_links and not ctx.company_phone:
        add("insufficient_activity", "Web nefunguje a nejsou známé jiné aktivní kanály")
    if not ctx.segment_enabled:
        add("unsuitable_segment", "Segment je v nastavení vypnutý")
    if opp is None:
        add("insufficient_data", f"Známé komponenty pokrývají jen {known_w * 100:.0f} % váhy (min. {min_known * 100:.0f} %)")

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "opportunity_score": None if opp is None else round(opp, 1),
        "confidence_score": round(confidence, 1),
        "category": category_for(opp),
        "design_gap": dg.score,
        "commercial_potential": cp.score,
        "buying_readiness": br.score,
        "service_fit": sf.score,
        "contactability": ct.score,
        "business_quality": bq.score,
        "website_quality": wq,
        "website_quality_basis": basis,
        "components": {k: c.to_dict() for k, c in comps.items()} | {"weights": weights, "known_weight_share": round(known_w, 2)},
        "recommended_service": service,
        "estimated_budget": estimated_budget(service, ctx.pricing),
        "outreach_reason": outreach_reason(ctx, comps, wq, basis),
        "disqualification_reasons": dq,
    }
