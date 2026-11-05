"""LinkedIn Prospecting Assistant – pouze generuje vyhledávací dotazy a odkazy.

Žádná automatizace LinkedIn: aplikace se nepřihlašuje, neprochází profily,
neposílá pozvánky ani zprávy. Uživatel otevře odkaz, ověří osobu a profil
ručně uloží.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from ..models import Company, Contact
from .normalize import normalize_name

PRIORITY_ROLES = ["Founder", "Co-founder", "Owner", "CEO", "Managing Director", "Marketing Manager", "E-commerce Manager"]
CZ_ROLES = ["majitel", "majitelka", "zakladatel", "zakladatelka", "jednatel", "jednatelka", "ředitel"]


def _clean_company(name: str) -> str:
    # bez právní formy – lidé ji na LinkedInu většinou neuvádějí
    import re

    return re.sub(r",?\s+(s\.?\s?r\.?\s?o\.?|spol\..*|a\.\s?s\.|v\.o\.s\.|k\.s\.)$", "", name, flags=re.I).strip()


def linkedin_links(company: Company, contact: Contact | None = None) -> list[dict[str, str]]:
    cname = _clean_company(company.name)
    links: list[dict[str, str]] = []
    if contact and contact.name:
        links.append({
            "label": f"Hledat osobu: {contact.name}",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(f'{contact.name} {cname}')}",
            "kind": "people",
        })
        links.append({
            "label": f"Hledat osobu (jen jméno): {contact.name}",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(contact.name)}",
            "kind": "people",
        })
    links.append({
        "label": "Lidé ve firmě (všechny role)",
        "url": f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(cname)}",
        "kind": "people",
    })
    roles = " OR ".join(PRIORITY_ROLES[:4] + CZ_ROLES[:3])
    links.append({
        "label": "Rozhodovací role (Founder / Owner / CEO / majitel)",
        "url": f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(f'{cname} ({roles})')}",
        "kind": "people",
    })
    links.append({
        "label": "Firemní stránka",
        "url": f"https://www.linkedin.com/search/results/companies/?keywords={quote_plus(cname)}",
        "kind": "company",
    })
    xray_roles = " OR ".join(f'"{r}"' for r in ["founder", "owner", "CEO", "majitel", "majitelka", "jednatel", "zakladatelka"])
    links.append({
        "label": "Google X-ray (veřejné profily)",
        "url": "https://www.google.com/search?q=" + quote_plus(f'site:linkedin.com/in "{cname}" ({xray_roles})'),
        "kind": "xray",
    })
    return links


def search_queries(company: Company) -> list[str]:
    cname = _clean_company(company.name)
    q = [f'"{cname}" founder', f'"{cname}" majitel', f'"{cname}" jednatel', f'"{cname}" CEO']
    if company.city:
        q.append(f'"{cname}" {company.city}')
    return q


def best_contact(company: Company) -> Contact | None:
    cands = [c for c in company.contacts if not c.do_not_contact]
    if not cands:
        return None

    def rank(c: Contact) -> tuple:
        role = (c.role or "").lower()
        prio = next((i for i, r in enumerate(["founder", "zakladatel", "majitel", "owner", "ceo", "jednatel", "ředitel",
                                                "managing", "marketing", "e-commerce", "společník"]) if r in role), 99)
        return (not c.is_primary, c.linkedin_url is None, not c.is_decision_maker, prio, not c.verified)

    return sorted(cands, key=rank)[0]


def same_person(a: str, b: str) -> bool:
    return normalize_name(a) == normalize_name(b)
