"""AI Sales Message Generator.

Zprávy vychází výhradně z ověřených faktů o firmě (web, registr, analýza).
Primární argument: „Vaše současná prezentace pravděpodobně neukazuje kvalitu
Vaší práce tak dobře, jak by mohla.“ – nikdy „Máte špatný web“.

Strategie (A/B testování):
A – Vizuální příležitost, B – Obchodní přínos, C – Personalizovaný návrh,
D – Rebranding, E – Konzultativní přístup.

Pokud je dostupný LLM (Ollama / API), generuje text model s kontrolou kvality.
Jinak se použije deterministický kompozitor, který skládá zprávu z faktů
(je to jasně označeno v poli `generator`).
"""
from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, Contact, OutreachMessage
from ..segments import get_segment
from ..settings_store import get_setting
from .linkedin import best_contact
from .llm import LLMError, extract_json, get_provider

log = logging.getLogger(__name__)

STRATEGIES = {
    "A": "Vizuální příležitost",
    "B": "Obchodní přínos",
    "C": "Personalizovaný návrh",
    "D": "Rebranding",
    "E": "Konzultativní přístup",
}
MESSAGE_TYPES = {
    "connection_request": "Žádost o spojení",
    "first_message": "První LinkedIn zpráva",
    "follow_up": "Follow-up",
    "alternative": "Alternativní varianta",
    "pitch": "Krátký obchodní argument",
}

BANNED_PHRASES = [
    "špatný web", "ošklivý web", "hrozný web", "zastaralý web", "doufám, že se máte dobře", "doufám, že se vám daří",
    "rád bych vám představil", "v dnešní digitální době", "v dnešním digitálním světě", "neváhejte", "revoluční",
    "posuňte své podnikání", "na další úroveň", "game changer", "jedinečná příležitost", "unikátní příležitost",
    "dovolte mi", "jako ai", "jako umělá inteligence", "synergie", "win-win", "garantujeme", "zaručeně",
    "zvýšíme vám tržby", "zvýšíme tržby", "zdvojnásobíme", "100 %", "úžasný", "fantastický", "naprosto skvělý",
    "ohromující", "v neposlední řadě", "potěšilo by mě", "omlouvám se, že ruším",
]
NUMERIC_PROMISE_RE = re.compile(r"(o\s*\d+\s*%|\d+\s*%\s*(více|víc)|\d+x\s*(více|víc))", re.I)

WORK_PHRASES = {
    "interior_design": ("vaše realizace interiérů", "interiéry, které navrhujete"),
    "premium_florist": ("vaše kytice a aranžmá", "floristickou práci"),
    "wedding_florist": ("svatební výzdobu, kterou děláte", "svatební floristiku"),
    "wedding_agency": ("svatby, které připravujete", "svatby, které organizujete"),
    "beauty_studio": ("výsledky vaší práce", "péči, kterou nabízíte"),
    "premium_cosmetics": ("ošetření, která nabízíte", "péči, kterou nabízíte"),
    "pilates_studio": ("atmosféru vašeho studia", "lekce, které vedete"),
    "fitness_studio": ("vaše studio a lekce", "tréninky, které nabízíte"),
    "custom_carpentry": ("vaše truhlářské realizace", "nábytek na míru, který vyrábíte"),
    "custom_kitchens": ("kuchyně, které realizujete", "kuchyně na míru"),
    "architecture_studio": ("vaše projekty", "architekturu, kterou navrhujete"),
    "design_brand": ("vaše produkty", "vaši značku"),
    "aesthetic_clinic": ("péči, kterou nabízíte", "vaše ošetření"),
    "premium_hair_salon": ("vaši práci", "střihy a barvení, které děláte"),
    "photographer": ("vaše fotky", "vaši fotografickou práci"),
    "wedding_photographer": ("vaše svatební fotky", "svatby, které fotíte"),
    "real_estate": ("nemovitosti, které nabízíte", "vaše služby"),
    "boutique_hotel": ("váš hotel", "atmosféru vašeho hotelu"),
    "premium_guesthouse": ("vaše ubytování", "atmosféru vašeho penzionu"),
    "wellness_center": ("vaše wellness", "procedury, které nabízíte"),
    "car_dealer": ("vozy, které nabízíte", "vaši nabídku"),
    "auto_detailing": ("výsledky vašeho detailingu", "vaši práci na autech"),
    "event_agency": ("akce, které připravujete", "vaše eventy"),
    "construction_company": ("vaše stavby", "realizace, které stavíte"),
}
DEFAULT_WORK = ("vaši práci", "služby, které nabízíte")

ISSUE_PHRASES = {
    "no_https": "prohlížeče u webu zobrazují upozornění „nezabezpečeno“, což může nové zákazníky odradit",
    "no_viewport": "na mobilu se web nezobrazuje tak dobře, jak by si vaše práce zasloužila",
    "mobile_overflow": "na mobilu se obsah nevejde na šířku obrazovky, a většina lidí dnes přichází právě z telefonu",
    "mobile_small_text": "na mobilu je text dost drobný a hůř se čte",
    "old_copyright": "web už pár let neprošel větší úpravou",
    "no_cta": "z úvodní stránky není hned jasné, jak si vás objednat nebo vás kontaktovat",
    "lowres_images": "některé fotky jsou na webu v nižším rozlišení, takže nevyzní tak, jak by mohly",
    "table_layout": "rozvržení webu odpovídá spíš starší generaci webů",
    "deprecated_html": "technicky je web postavený ještě starším způsobem",
    "slow": "web se načítá poměrně dlouho",
    "thin_content": "na webu je o vašich službách jen málo informací",
    "hard_to_contact": "na webu se dá jen obtížně najít, jak vás kontaktovat",
    "site_builder": "web běží na šablonovém builderu, který designově dost omezuje",
    "broken_images": "některé obrázky na webu se nenačítají",
}
SIGNAL_PHRASES = {
    "new_branch": "Všiml jsem si, že otevíráte novou provozovnu",
    "new_service": "Všiml jsem si, že máte v nabídce novinky",
    "new_product": "Všiml jsem si, že představujete nové produkty",
    "rebranding": "Všiml jsem si, že u vás probíhají změny ve vizuální identitě",
    "expansion": "Všiml jsem si, že se rozšiřujete",
    "hiring": "Všiml jsem si, že hledáte nové kolegy do týmu",
    "young_company": "Vidím, že firma funguje teprve krátce",
}


@dataclass
class Fact:
    key: str
    text: str
    source: str
    data: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "text": self.text, "source": self.source}


def gather_facts(db: Session, company: Company, contact: Contact | None) -> list[Fact]:
    from .pipeline import current_score, latest_audit, latest_visual, latest_website

    facts: list[Fact] = [Fact("company_name", company.name, "CRM")]
    seg = get_segment(company.segment_key)
    if seg:
        facts.append(Fact("segment", seg.label, "klasifikace"))
    if company.city:
        facts.append(Fact("city", company.city, "adresa"))
    if contact:
        facts.append(Fact("contact", f"{contact.name}{' – ' + contact.role if contact.role else ''}",
                          "ověřeno" if contact.verified else contact.source))
    w = latest_website(company)
    ex = (w.extracted if w and w.reachable else {}) or {}
    if w:
        facts.append(Fact("website", w.final_url or w.url, "web"))
    if ex.get("h1"):
        facts.append(Fact("headline", ex["h1"][0][:140], "úvodní stránka webu"))
    if ex.get("h2"):
        facts.append(Fact("sections", ", ".join(ex["h2"][:6])[:300], "nadpisy na webu"))
    if "portfolio" in (ex.get("pages_crawled") or []) and ex.get("portfolio_image_count"):
        facts.append(Fact("portfolio", f"Na webu mají sekci realizací/portfolia s {ex['portfolio_image_count']} obrázky", "web"))
    q = ex.get("quality") or {}
    if q.get("testimonials"):
        sn = (ex.get("quality_snippets") or {}).get("testimonials") or []
        facts.append(Fact("testimonials", "Na webu mají reference / recenze klientů", "web" + (f" – úryvek: „{sn[0][:120]}…“" if sn else "")))
    if q.get("awards"):
        sn = (ex.get("quality_snippets") or {}).get("awards") or []
        facts.append(Fact("awards", "Na webu zmiňují ocenění", "web" + (f" – úryvek: „{sn[0][:120]}…“" if sn else "")))
    if q.get("weddings") and company.segment_key not in ("wedding_agency", "wedding_florist", "wedding_photographer"):
        facts.append(Fact("weddings", "Dělají i svatební zakázky", "web"))
    if ex.get("years_experience"):
        facts.append(Fact("experience", f"Uvádí {ex['years_experience']} let zkušeností", "web", {"years": ex["years_experience"]}))
    elif ex.get("since_year"):
        facts.append(Fact("experience", f"Fungují od roku {ex['since_year']}", "web", {"since": ex["since_year"]}))
    elif company.founded_on:
        facts.append(Fact("experience", f"Firma vznikla v roce {company.founded_on[:4]}", "ARES", {"since": int(company.founded_on[:4])}))
    socials = {**(company.social_links or {}), **(ex.get("socials") or {})}
    if "instagram" in socials:
        facts.append(Fact("instagram", "Mají Instagram", "odkaz na webu"))
    if ex.get("copyright_year"):
        facts.append(Fact("copyright", f"Copyright v patičce webu: {ex['copyright_year']}", "web"))
    if ex.get("cms"):
        facts.append(Fact("cms", f"Web běží na {ex['cms']}", "technická analýza"))
    audit = latest_audit(db, company)
    if audit:
        # pořadí podle toho, co zákazník na webu skutečně pozná (ne podle technické závažnosti)
        relevance = ["no_viewport", "mobile_overflow", "no_https", "no_cta", "lowres_images", "broken_images",
                     "mobile_small_text", "old_copyright", "hard_to_contact", "thin_content", "table_layout", "slow",
                     "site_builder", "deprecated_html"]
        ordered = sorted((i for i in audit.issues or [] if i["code"] in ISSUE_PHRASES), key=lambda i: relevance.index(i["code"])
                         if i["code"] in relevance else 99)
        for i in ordered[:4]:
            if i["code"] in ISSUE_PHRASES:
                facts.append(Fact(f"issue:{i['code']}", ISSUE_PHRASES[i["code"]], f"technický audit: {i['detail']}"))
        if audit.screenshots:
            facts.append(Fact("screenshots", "Prošli jsme web na počítači i na mobilu", "screenshoty"))
    va = latest_visual(db, company)
    if va and va.status == "complete":
        for t in (va.top_issues or [])[:3]:
            facts.append(Fact("visual_issue", t, f"vizuální analýza ({va.provider}, expertní odhad)"))
        for t in (va.strengths or [])[:2]:
            facts.append(Fact("visual_strength", t, "vizuální analýza (expertní odhad)"))
        brand = next((c for c in va.criteria or [] if c.get("key") == "brand_consistency"), None)
        if brand and brand.get("score") is not None and brand["score"] < 45:
            facts.append(Fact("brand_weak", brand.get("observation") or "Branding působí nejednotně", "vizuální analýza"))
    for s in sorted(company.signals, key=lambda x: -x.strength)[:3]:
        if s.signal_type in SIGNAL_PHRASES:
            facts.append(Fact(f"signal:{s.signal_type}", f"{s.description}: {(s.evidence or '')[:160]}", s.source_url or "web"))
    sc = current_score(db, company.id)
    if sc and sc.recommended_service:
        facts.append(Fact("recommended_service", sc.estimated_budget["label"] if sc.estimated_budget else sc.recommended_service, "scoring"))
    if not company.website_url:
        facts.append(Fact("no_website", "Firma nemá vlastní web (jen profily / katalogy)", "CRM"))
    return facts


def choose_strategy(db: Session, company: Company, facts: list[Fact]) -> str:
    """Automatická volba strategie podle faktů + průzkum (epsilon-greedy) podle výsledků."""
    from .learning import strategy_performance

    keys = {f.key.split(":")[0] for f in facts}
    if "brand_weak" in keys or any(f.key == "signal:rebranding" for f in facts):
        base = "D"
    elif any(k == "signal" for k in keys):
        base = "B"
    elif "portfolio" in keys and ("visual_issue" in keys or "issue" in keys):
        base = "A"
    elif "visual_issue" in keys:
        base = "C"
    else:
        base = "E"
    perf = strategy_performance(db)
    total_sent = sum(p["sent"] for p in perf.values())
    if total_sent >= 30 and random.random() < 0.3:
        best = max(perf.items(), key=lambda kv: kv[1]["score"])[0]
        return best
    if random.random() < 0.15:
        return random.choice(list(STRATEGIES))
    return base


# ---------------------------------------------------------------------------
def quality_check(msg_type: str, text: str, limits: dict[str, int], facts: list[Fact]) -> list[str]:
    warnings = []
    low = text.lower()
    for b in BANNED_PHRASES:
        if b in low:
            warnings.append(f"Obsahuje nevhodnou frázi: „{b}“")
    if NUMERIC_PROMISE_RE.search(text):
        warnings.append("Obsahuje číselný slib výsledku bez důkazu")
    if msg_type == "connection_request" and len(text) > limits["connection_request"]:
        warnings.append(f"Žádost o spojení má {len(text)} znaků (limit {limits['connection_request']})")
    if msg_type in ("first_message", "alternative") and len(text) > limits["first_message"]:
        warnings.append(f"Zpráva má {len(text)} znaků (doporučeno max. {limits['first_message']})")
    if text.count("!") > 1:
        warnings.append("Příliš mnoho vykřičníků")
    name = facts[0].text.lower() if facts else ""
    short = re.sub(r",?\s+(s\.r\.o\.|a\.s\.).*$", "", name).strip()
    if msg_type in ("first_message", "alternative") and short and short[:10] not in low:
        # personalizace: zmínka o firmě nebo konkrétním faktu
        specific = [f for f in facts if f.key.startswith(("issue", "visual_issue", "portfolio", "signal", "headline", "testimonials", "awards"))]
        if not specific:
            warnings.append("Zpráva nemá dost konkrétních faktů o firmě")
    return warnings


def _short_name(company: Company) -> str:
    return re.sub(r",?\s+(s\.\s?r\.\s?o\.|spol\..*|a\.\s?s\.|v\.o\.s\.)\s*$", "", company.name, flags=re.I).strip()


def compose_fallback(company: Company, contact: Contact | None, facts: list[Fact], strategy: str,
                     sender: str, agency: dict[str, Any]) -> dict[str, str]:
    """Deterministický kompozitor z faktů (použije se, když není dostupný LLM)."""
    name = _short_name(company)
    work, work2 = WORK_PHRASES.get(company.segment_key or "", DEFAULT_WORK)
    fk = {f.key: f for f in facts}
    issues = [f.text for f in facts if f.key.startswith("issue:")]
    vis_issues = [f.text for f in facts if f.key == "visual_issue"]
    signal = next((f for f in facts if f.key.startswith("signal:")), None)
    signal_line = SIGNAL_PHRASES.get(signal.key.split(":")[1]) if signal else None
    portfolio = fk.get("portfolio")
    proof_key = next((k for k in ("testimonials", "awards", "experience") if k in fk), None)
    greeting = "Dobrý den,"
    sign = f"\n\n{sender}" if sender else ""
    obs = issues[0] if issues else (vis_issues[0][0].lower() + vis_issues[0][1:] if vis_issues else None)
    no_web = "no_website" in fk
    own_domain = (company.domain or "").lower()
    portfolio_ref = next((p for p in agency.get("portfolio", []) if p.get("segment") == company.segment_key
                          and not (own_domain and own_domain in (p.get("url") or "").lower())), None)
    ref_line = f" Podobně jsme nedávno dělali web pro {portfolio_ref['name']} ({portfolio_ref['url'].replace('https://', '')})." if portfolio_ref else ""
    speed = "Web umíme mít venku za 2–3 týdny a komunikujete přímo s tím, kdo ho navrhuje."

    # ---- žádost o spojení
    if signal_line:
        conn = f"{greeting} {signal_line[0].lower() + signal_line[1:]} – gratuluji. Navrhuji weby pro firmy z vašeho oboru a rád bych se s vámi spojil."
    elif no_web:
        conn = f"{greeting} narazil jsem na {name} a líbí se mi {work}. Navrhuji weby pro menší firmy a rád bych se s vámi spojil."
    else:
        conn = f"{greeting} prošel jsem si web {name} a podíval se na {work}. Navrhuji weby pro firmy z vašeho oboru – rád bych se spojil."
    if len(conn) > 280:
        conn = f"{greeting} zaujala mě práce {name}. Navrhuji weby pro firmy z vašeho oboru a rád bych se s vámi spojil."

    # ---- hlavní zprávy dle strategie
    strength = ""
    if portfolio:
        strength = f"Na vašem webu jsem si prohlížel {work} a je vidět, že za tím je kvalitní práce."
    elif proof_key == "testimonials":
        strength = f"Prohlížel jsem si {work} a recenze vašich klientů – je vidět, že lidé jsou s vaší prací spokojení."
    elif proof_key == "awards":
        strength = f"Prohlížel jsem si {work} a zaujalo mě i ocenění, které na webu zmiňujete."
    elif proof_key == "experience":
        d = fk["experience"].data or {}
        yrs = d.get("years") or (date.today().year - d["since"] if d.get("since") else None)
        strength = (f"Prohlížel jsem si {work} – a {yrs} let v oboru je na nich znát." if yrs and yrs >= 3
                    else f"Prohlížel jsem si {work} a líbí se mi, jak k oboru přistupujete.")
    else:
        strength = f"Prohlížel jsem si {work} a líbí se mi, jak k oboru přistupujete."
    issue_txt = f" Při procházení na počítači i na mobilu jsem si ale všiml, že {obs}." if obs else ""
    core = ("Myslím, že současná prezentace neukazuje kvalitu vaší práce tak dobře, jak by mohla – "
            "a právě podle webu si vás dnes noví klienti často vybírají.")
    if no_web:
        issue_txt = " Nenašel jsem ale váš vlastní web – jen profily na sítích a v katalozích."
        core = "Vlastní web by vaší práci dal prostor, který profily na sítích nedají, a usnadnil by lidem poptávku."
    benefits = {
        "A": "Napadlo mě, jak by šlo portfolio ukázat výrazněji – větší fotky, přehledné realizace a jasná cesta k poptávce.",
        "B": "Lepší prezentace obvykle znamená víc důvěry u nových zákazníků a snazší poptávky – hlavně z mobilu.",
        "C": f"Klidně vám pošlu krátký návrh, jak by mohla vypadat úvodní stránka {name} – nezávazně a zdarma.",
        "D": "Často pomůže sjednotit vizuální identitu – logo, barvy a typografii – a na ni navázat nový web.",
        "E": "Nechci nic nabízet naslepo – spíš by mě zajímalo, jestli je web pro vás téma a co od něj čekáte.",
    }
    cta = {
        "A": "Mám vám poslat pár konkrétních nápadů?",
        "B": "Dávalo by smysl si o tom krátce napsat?",
        "C": "Mám ho připravit?",
        "D": "Je to pro vás téma?",
        "E": "Jak to máte vy – řešíte web teď, nebo je to spíš na později?",
    }
    opener = f"{signal_line} – gratuluji. " if signal_line and strategy in ("B", "D") else ""
    first = (f"{greeting}\n\n{opener}{strength}{issue_txt}\n\n{core} {benefits[strategy]}\n\n"
             f"{speed}{ref_line} {cta[strategy]}{sign}")
    alt_strategy = {"A": "E", "B": "C", "C": "A", "D": "B", "E": "C"}[strategy]
    alternative = (f"{greeting}\n\nnarazil jsem na {name} a podíval se na {work}.{issue_txt or ''}\n\n{benefits[alt_strategy]} "
                   f"{cta[alt_strategy]}{sign}")
    offer = "Návrh úvodní stránky vám rád pošlu i bez dalších závazků. " if strategy == "C" else ""
    follow = (f"{greeting}\n\njen se krátce připomínám ohledně webu {name}. {offer}"
              f"Pokud to teď není téma, úplně to chápu – dejte vědět a nebudu dál psát.{sign}")
    proof_txt = "; ".join(fk[k].text for k in ("portfolio", "testimonials", "awards", "experience") if k in fk)
    pitch_parts = [f"{name} ({fk['segment'].text if 'segment' in fk else 'obor neurčen'}): {proof_txt or 'kvalitu podnikání zatím nelze doložit'}."]
    if obs:
        pitch_parts.append(f"Zjištění: {obs}.")
    rec = fk.get("recommended_service")
    pitch_parts.append("Firma nemá vlastní web – příležitost pro novou prezentaci." if no_web else
                       "Současná prezentace pravděpodobně neukazuje kvalitu jejich práce tak dobře, jak by mohla.")
    if rec:
        pitch_parts.append(f"Doporučená nabídka: {rec.text}.")
    pitch = " ".join(pitch_parts)
    return {"connection_request": conn, "first_message": first, "follow_up": follow, "alternative": alternative, "pitch": pitch}


SYSTEM_PROMPT = """Jsi zkušený obchodník a copywriter malé české webové agentury Project Two. Píšeš LinkedIn zprávy majitelům menších firem.
Styl: profesionální, přirozený, lidský, stručný, sebevědomý. Žádný agresivní prodej, žádné přehnané komplimenty, žádná AI klišé.
Piš česky, v první osobě jednotného čísla (jeden člověk z agentury), vykej. Oslovení „Dobrý den,“ (bez jména v 5. pádě).
NIKDY nepiš, že mají „špatný/zastaralý/ošklivý web“. Primární myšlenka: současná prezentace pravděpodobně neukazuje kvalitu jejich práce tak dobře, jak by mohla.
Používej POUZE fakta ze seznamu. Nic si nevymýšlej (žádná čísla, recenze, jména, zakázky, které nejsou ve faktech). Neslibuj konkrétní nárůst tržeb.
Vysvětli obchodní hodnotu (lepší prezentace portfolia, důvěryhodnost, přehlednější nabídka, snazší poptávky, mobil, profesionálnější branding) – vyber to, co sedí na fakta.
Zakázané fráze: """ + ", ".join(BANNED_PHRASES[:20]) + """.
Odpovídej pouze validním JSON."""


def build_llm_prompt(company: Company, facts: list[Fact], strategy: str, agency: dict[str, Any], limits: dict[str, int],
                     sender: str) -> str:
    fact_lines = "\n".join(f"- [{f.key}] {f.text} (zdroj: {f.source})" for f in facts)
    agency_lines = "\n".join(f"- {x}" for x in agency.get("facts", []))
    portfolio = ", ".join(f"{p['name']} ({p['url']})" for p in agency.get("portfolio", []))
    return f"""FAKTA O FIRMĚ (ověřená):
{fact_lines}

O NÁS (Project Two, {agency.get('url')}):
{agency_lines}
Ukázky naší práce: {portfolio}

STRATEGIE: {strategy} – {STRATEGIES[strategy]}
- A: zaměř se na vizuální příležitost (jak lépe ukázat jejich práci/portfolio)
- B: zaměř se na obchodní přínos (důvěra, poptávky, mobil)
- C: nabídni konkrétní nezávazný návrh (např. skicu úvodní stránky)
- D: rebranding (sjednocení identity + web)
- E: konzultativní – zeptej se na jejich situaci, nic netlač

Vytvoř JSON:
{{
 "connection_request": "žádost o spojení, max {limits['connection_request']} znaků, bez prodeje, s jedním konkrétním detailem",
 "first_message": "první zpráva po přijetí spojení, max {limits['first_message']} znaků, 2–4 krátké odstavce, konkrétní pozorování z faktů, obchodní hodnota, jemná výzva k odpovědi",
 "follow_up": "krátký follow-up (max 350 znaků), zdvořilý, nabídni, že už nebudeš psát, pokud to není téma",
 "alternative": "alternativní verze první zprávy s jiným úhlem (strategie {('E' if strategy != 'E' else 'C')}), max {limits['first_message']} znaků",
 "pitch": "2–3 věty interního obchodního argumentu, proč je firma vhodný klient a co jí nabídnout",
 "facts_used": ["klíče faktů, které jsi použil"]
}}
Podpis: {sender or '(bez podpisu)'}."""


def generate_message_set(db: Session, company: Company, strategy: str | None = None, contact: Contact | None = None,
                         use_llm: bool = True) -> list[OutreachMessage]:
    msg_cfg = get_setting(db, "messages")
    agency = get_setting(db, "agency")
    limits = {"connection_request": int(msg_cfg["connection_request_max_chars"]),
              "first_message": int(msg_cfg["first_message_max_chars"])}
    sender = (msg_cfg.get("sender_name") or "").strip()
    contact = contact or best_contact(company)
    facts = gather_facts(db, company, contact)
    if (not strategy or strategy == "auto") and company.campaign and company.campaign.default_strategy:
        strategy = company.campaign.default_strategy
    if not strategy or strategy == "auto":
        strategy = choose_strategy(db, company, facts)
    strategy = strategy.upper()
    if strategy not in STRATEGIES:
        raise ValueError("Neplatná strategie")

    texts: dict[str, str] | None = None
    generator = "composer:v1"
    used_keys: list[str] = [f.key for f in facts]
    provider, note = get_provider("text") if use_llm else (None, "LLM vypnut")
    if provider is not None:
        prompt = build_llm_prompt(company, facts, strategy, agency, limits, sender)
        feedback = ""
        for _ in range(2):
            try:
                resp = provider.complete(SYSTEM_PROMPT, prompt + feedback, json_mode=True, max_tokens=1800, temperature=0.6)
                data = extract_json(resp.text)
                cand = {k: str(data.get(k) or "").strip() for k in MESSAGE_TYPES}
                if not all(cand.values()):
                    raise LLMError("Chybí některé typy zpráv")
                problems = []
                for k, v in cand.items():
                    problems += quality_check(k, v, limits, facts)
                if problems and not feedback:
                    feedback = "\n\nPOZOR, oprav tyto problémy: " + "; ".join(problems[:6])
                    texts = cand
                    continue
                texts = cand
                generator = f"llm:{resp.provider}:{resp.model}"
                used_keys = [k for k in (data.get("facts_used") or []) if isinstance(k, str)] or used_keys
                break
            except LLMError as exc:
                log.warning("LLM generování selhalo: %s", exc)
        if texts is not None and generator == "composer:v1":
            generator = f"llm:{provider.name}:{provider.model}"
    if texts is None:
        texts = compose_fallback(company, contact, facts, strategy, sender, agency)
        generator = "composer:v1 (bez LLM – " + note[:60] + ")"

    # archivuj předchozí koncepty stejného typu
    for old in db.scalars(select(OutreachMessage).where(OutreachMessage.company_id == company.id, OutreachMessage.status == "draft")):
        old.status = "archived"
    out = []
    fact_map = {f.key: f.to_dict() for f in facts}
    for mtype, text in texts.items():
        warnings = quality_check(mtype, text, limits, facts)
        m = OutreachMessage(
            company_id=company.id, contact_id=contact.id if contact else None, campaign_id=company.campaign_id,
            channel="linkedin", strategy=strategy, message_type=mtype, content=text.strip(),
            facts_used=[fact_map[k] for k in used_keys if k in fact_map] or list(fact_map.values()),
            generator=generator, quality_warnings=warnings, status="draft",
        )
        db.add(m)
        out.append(m)
    db.flush()
    return out
