"""Regiony – kraje ČR a SR (ISO 3166-2) a hlavní města pro vyhledávání."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    code: str  # ISO 3166-2
    name: str
    country: str
    cities: tuple[str, ...]
    default_priority: int  # 1–5 (5 = nejvyšší)


REGIONS: list[Region] = [
    Region("CZ-10", "Hlavní město Praha", "CZ", ("Praha",), 5),
    Region("CZ-64", "Jihomoravský kraj", "CZ", ("Brno", "Znojmo", "Hodonín", "Břeclav", "Blansko", "Vyškov"), 5),
    Region("CZ-20", "Středočeský kraj", "CZ", ("Kladno", "Mladá Boleslav", "Příbram", "Kolín", "Beroun", "Benešov",
                                               "Říčany", "Černošice", "Brandýs nad Labem-Stará Boleslav", "Mělník"), 4),
    Region("CZ-80", "Moravskoslezský kraj", "CZ", ("Ostrava", "Opava", "Frýdek-Místek", "Havířov", "Karviná",
                                                  "Nový Jičín"), 4),
    Region("CZ-32", "Plzeňský kraj", "CZ", ("Plzeň", "Klatovy", "Domažlice", "Rokycany"), 3),
    Region("CZ-31", "Jihočeský kraj", "CZ", ("České Budějovice", "Tábor", "Písek", "Český Krumlov", "Strakonice"), 3),
    Region("CZ-71", "Olomoucký kraj", "CZ", ("Olomouc", "Prostějov", "Přerov", "Šumperk"), 3),
    Region("CZ-52", "Královéhradecký kraj", "CZ", ("Hradec Králové", "Trutnov", "Náchod", "Jičín"), 3),
    Region("CZ-53", "Pardubický kraj", "CZ", ("Pardubice", "Chrudim", "Svitavy", "Ústí nad Orlicí"), 3),
    Region("CZ-51", "Liberecký kraj", "CZ", ("Liberec", "Jablonec nad Nisou", "Česká Lípa"), 3),
    Region("CZ-72", "Zlínský kraj", "CZ", ("Zlín", "Uherské Hradiště", "Vsetín", "Kroměříž"), 3),
    Region("CZ-63", "Kraj Vysočina", "CZ", ("Jihlava", "Třebíč", "Havlíčkův Brod", "Žďár nad Sázavou"), 2),
    Region("CZ-42", "Ústecký kraj", "CZ", ("Ústí nad Labem", "Teplice", "Děčín", "Most", "Chomutov", "Litoměřice"), 2),
    Region("CZ-41", "Karlovarský kraj", "CZ", ("Karlovy Vary", "Cheb", "Mariánské Lázně", "Sokolov"), 2),
    # Slovensko
    Region("SK-BL", "Bratislavský kraj", "SK", ("Bratislava",), 4),
    Region("SK-KI", "Košický kraj", "SK", ("Košice",), 3),
    Region("SK-ZI", "Žilinský kraj", "SK", ("Žilina", "Martin"), 2),
    Region("SK-BC", "Banskobystrický kraj", "SK", ("Banská Bystrica",), 2),
    Region("SK-TA", "Trnavský kraj", "SK", ("Trnava",), 2),
    Region("SK-TC", "Trenčiansky kraj", "SK", ("Trenčín",), 2),
    Region("SK-NI", "Nitriansky kraj", "SK", ("Nitra",), 2),
    Region("SK-PV", "Prešovský kraj", "SK", ("Prešov", "Poprad"), 2),
]

REGION_BY_CODE = {r.code: r for r in REGIONS}

# Psč prefix -> kraj (přibližné mapování dle prvních dvou číslic PSČ ČR)
_PSC_PREFIX = {
    "1": "CZ-10",
    "25": "CZ-20", "26": "CZ-20", "27": "CZ-20", "28": "CZ-20", "29": "CZ-20",
    "30": "CZ-32", "31": "CZ-32", "32": "CZ-32", "33": "CZ-32", "34": "CZ-32",
    "35": "CZ-41", "36": "CZ-41",
    "37": "CZ-31", "38": "CZ-31", "39": "CZ-31",
    "40": "CZ-42", "41": "CZ-42", "43": "CZ-42", "44": "CZ-42",
    "46": "CZ-51", "47": "CZ-51", "51": "CZ-51",
    "50": "CZ-52", "54": "CZ-52", "55": "CZ-52",
    "53": "CZ-53", "56": "CZ-53", "57": "CZ-53",
    "58": "CZ-63", "59": "CZ-63", "67": "CZ-63",
    "60": "CZ-64", "61": "CZ-64", "62": "CZ-64", "63": "CZ-64", "64": "CZ-64", "66": "CZ-64", "68": "CZ-64", "69": "CZ-64",
    "75": "CZ-71", "77": "CZ-71", "78": "CZ-71", "79": "CZ-71",
    "76": "CZ-72",
    "70": "CZ-80", "71": "CZ-80", "72": "CZ-80", "73": "CZ-80", "74": "CZ-80",
}


def region_from_postcode(postcode: str | None) -> str | None:
    if not postcode:
        return None
    digits = "".join(ch for ch in postcode if ch.isdigit())
    if len(digits) != 5:
        return None
    if digits[0] == "1":
        return "CZ-10"
    return _PSC_PREFIX.get(digits[:2])


def region_from_city(city: str | None) -> str | None:
    if not city:
        return None
    c = city.strip().lower()
    if c.startswith("praha"):
        return "CZ-10"
    for r in REGIONS:
        for rc in r.cities:
            if rc.lower() == c:
                return r.code
    return None
