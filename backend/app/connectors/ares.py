"""ARES – Administrativní registr ekonomických subjektů (oficiální veřejné REST API MF ČR).

Používá se hlavně pro obohacení (IČO, právní forma, datum vzniku, NACE, stav subjektu)
a pro identifikaci statutárních orgánů z veřejného rejstříku (jednatelé = rozhodovací osoby).
Z osobních údajů ukládáme pouze jméno a funkci (minimalizace dat).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..config import get_settings
from ..regions import region_from_postcode
from ..services.normalize import normalize_ico, normalize_name
from ..services.http_client import api_request
from .base import AvailabilityResult, Connector, ConnectorError, DiscoveryQuery, RawCompany

log = logging.getLogger(__name__)

LEGAL_FORMS = {
    "101": "Fyzická osoba podnikající (OSVČ)",
    "105": "Fyzická osoba podnikající (OSVČ)",
    "107": "Zemědělský podnikatel",
    "111": "Veřejná obchodní společnost",
    "112": "Společnost s ručením omezeným",
    "113": "Komanditní společnost",
    "121": "Akciová společnost",
    "141": "Obecně prospěšná společnost",
    "205": "Družstvo",
    "706": "Spolek",
    "751": "Zájmové sdružení",
}

ARES_KRAJ_TO_ISO = {
    19: "CZ-10", 27: "CZ-20", 35: "CZ-31", 43: "CZ-32", 51: "CZ-41", 60: "CZ-42", 78: "CZ-51", 86: "CZ-52",
    94: "CZ-53", 108: "CZ-63", 116: "CZ-64", 124: "CZ-71", 141: "CZ-72", 132: "CZ-80",
}

DECISION_KEYWORDS = ("jednatel", "předseda", "ředitel", "společník", "prokurist", "statutární")


class AresConnector(Connector):
    key = "ares"
    name = "ARES – registr ekonomických subjektů"
    kind = "registry"
    access_policy = "Oficiální bezplatné REST API Ministerstva financí ČR (ares.gov.cz). Veřejná data, fair-use."
    rate_limit_per_minute = 30
    supports_discovery = True

    def __init__(self) -> None:
        self.base_url = get_settings().ares_base_url

    def _get(self, path: str) -> dict | None:
        r = api_request("GET", f"{self.base_url}{path}", rate_key="ares", min_interval=self.min_interval, timeout=20)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise ConnectorError(f"ARES HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def check_availability(self) -> AvailabilityResult:
        if get_settings().disable_network:
            return AvailabilityResult("unavailable", "Síť je vypnutá")
        try:
            d = self._get("/ekonomicke-subjekty/00006947")  # Ministerstvo financí
            return AvailabilityResult("ok" if d else "error", "ARES odpovídá" if d else "Neočekávaná odpověď")
        except Exception as exc:  # noqa: BLE001
            return AvailabilityResult("unavailable", str(exc)[:300])

    # ------------------------------------------------------------------
    @staticmethod
    def parse_subject(d: dict) -> dict[str, Any]:
        sidlo = d.get("sidlo") or {}
        street = sidlo.get("nazevUlice") or sidlo.get("nazevCastiObce")
        num = sidlo.get("cisloDomovni")
        if num and sidlo.get("cisloOrientacni"):
            num = f"{num}/{sidlo.get('cisloOrientacni')}{sidlo.get('cisloOrientacniPismeno') or ''}"
        if street and num:
            street = f"{street} {num}"
        psc = sidlo.get("psc") or sidlo.get("pscTxt")
        psc = str(psc).zfill(5) if psc else None
        regs = d.get("seznamRegistraci") or {}
        active = any(v == "AKTIVNI" for k, v in regs.items() if k in ("stavZdrojeRos", "stavZdrojeRzp", "stavZdrojeVr", "stavZdrojeRes"))
        nace = d.get("czNace2008") or d.get("czNace") or []
        return {
            "ico": d.get("ico"),
            "legal_name": d.get("obchodniJmeno"),
            "legal_form_code": d.get("pravniForma"),
            "legal_form": LEGAL_FORMS.get(str(d.get("pravniForma")), f"Právní forma {d.get('pravniForma')}"),
            "founded_on": d.get("datumVzniku"),
            "terminated_on": d.get("datumZaniku"),
            "street": street,
            "city": sidlo.get("nazevObce"),
            "postcode": psc,
            "country": sidlo.get("kodStatu") or "CZ",
            "region_code": ARES_KRAJ_TO_ISO.get(sidlo.get("kodKraje")) or region_from_postcode(psc),
            "address_text": sidlo.get("textovaAdresa"),
            "nace": [str(n) for n in nace],
            "active": active and not d.get("datumZaniku"),
            "dic": d.get("dic"),
        }

    def get_by_ico(self, ico: str) -> dict[str, Any] | None:
        ico_n = normalize_ico(ico)
        if not ico_n:
            return None
        d = self._get(f"/ekonomicke-subjekty/{ico_n}")
        return self.parse_subject(d) if d else None

    def find_by_name(self, name: str, city: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"obchodniJmeno": name, "start": 0, "pocet": limit}
        r = api_request("POST", f"{self.base_url}/ekonomicke-subjekty/vyhledat", rate_key="ares",
                        min_interval=self.min_interval, json=body, timeout=20)
        if r.status_code >= 400:
            return []
        out = [self.parse_subject(s) for s in r.json().get("ekonomickeSubjekty", [])]
        if city:
            c = normalize_name(city)
            out.sort(key=lambda x: 0 if normalize_name(x.get("city") or "").startswith(c[:5]) else 1)
        return out

    def statutory_persons(self, ico: str) -> dict[str, Any]:
        """Aktuální členové statutárních orgánů + základní kapitál z veřejného rejstříku."""
        ico_n = normalize_ico(ico)
        if not ico_n:
            return {"persons": [], "capital_czk": None}
        d = self._get(f"/ekonomicke-subjekty-vr/{ico_n}")
        if not d or not d.get("zaznamy"):
            return {"persons": [], "capital_czk": None}
        z = next((x for x in d["zaznamy"] if x.get("primarniZaznam")), d["zaznamy"][0])
        persons: list[dict[str, str]] = []
        for organ in z.get("statutarniOrgany", []) or []:
            if organ.get("datumVymazu"):
                continue
            for clen in organ.get("clenoveOrganu", []) or []:
                if clen.get("datumVymazu"):
                    continue
                fo = clen.get("fyzickaOsoba")
                if not fo:
                    continue
                name = " ".join(p.strip().title() for p in [fo.get("jmeno", ""), fo.get("prijmeni", "")] if p)
                funkce = ((clen.get("clenstvi") or {}).get("funkce") or {}).get("nazev") or clen.get("nazevAngazma")
                persons.append({"name": name, "role": (funkce or "Statutární orgán").capitalize(),
                                "organ": organ.get("nazevOrganu", "")})
        for spol in z.get("spolecnici", []) or []:
            if spol.get("datumVymazu"):
                continue
            for s in spol.get("spolecnik", []) or []:
                if s.get("datumVymazu"):
                    continue
                fo = (s.get("osoba") or {}).get("fyzickaOsoba")
                if fo:
                    name = " ".join(p.strip().title() for p in [fo.get("jmeno", ""), fo.get("prijmeni", "")] if p)
                    if name and not any(p["name"] == name for p in persons):
                        persons.append({"name": name, "role": "Společník", "organ": "Společníci"})
        capital = None
        for k in z.get("zakladniKapital", []) or []:
            if k.get("datumVymazu"):
                continue
            val = ((k.get("vklad") or {}).get("hodnota") or "").split(";")[0]
            if val.isdigit():
                capital = int(val)
                break
        return {"persons": persons[:10], "capital_czk": capital, "status": z.get("stavSubjektu")}

    # ------------------------------------------------------------------
    def search(self, query: DiscoveryQuery):
        """Discovery podle klíčového slova v obchodním jménu (ARES neobsahuje weby – nutné dohledání).

        ARES filtruje sídlo jen podle obce, kraj proto filtrujeme sami a stránkujeme (max. 5 × 100 záznamů).
        """
        if not query.keyword:
            return
        yielded = 0
        for page in range(5):
            body: dict[str, Any] = {"obchodniJmeno": query.keyword, "start": page * 100, "pocet": 100}
            r = api_request("POST", f"{self.base_url}/ekonomicke-subjekty/vyhledat", rate_key="ares",
                            min_interval=self.min_interval, json=body, timeout=30)
            if r.status_code >= 400:
                raise ConnectorError(f"ARES HTTP {r.status_code}")
            data = r.json()
            subjects = data.get("ekonomickeSubjekty", [])
            for s in subjects:
                p = self.parse_subject(s)
                if not p["active"]:
                    continue
                if query.region_code and p["region_code"] != query.region_code:
                    continue
                if query.city and normalize_name(p.get("city") or "")[:5] != normalize_name(query.city)[:5]:
                    continue
                yield RawCompany(
                    source_key="ares", external_id=p["ico"], name=p["legal_name"], segment_key=query.segment_key,
                    country=p["country"], region_code=p["region_code"], city=p["city"], street=p["street"],
                    postcode=p["postcode"], ico=p["ico"], legal_form=p["legal_form"], founded_on=p["founded_on"],
                    source_url=f"https://ares.gov.cz/ekonomicke-subjekty?ico={p['ico']}", raw=p,
                )
                yielded += 1
                if yielded >= query.limit:
                    return
            if (page + 1) * 100 >= int(data.get("pocetCelkem") or 0):
                return


def years_since(iso_date: str | None) -> float | None:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    return (date.today() - d).days / 365.25
