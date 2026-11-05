"""Cílové segmenty – počáteční obchodní hypotézy.

Každý segment obsahuje:
- tier (1 = nejvyšší priorita),
- OSM tagy a regex na název pro Overpass,
- vyhledávací dotazy pro vyhledávací API,
- základní ekonomickou hodnotu (typický cenový segment služeb),
- důležitost vizuální prezentace pro obor (váha pro Service Fit).

Priority segmentů se dají upravovat v nastavení a systém navrhuje úpravy podle
skutečných výsledků oslovení (viz services/learning.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    tier: int
    osm_tags: tuple[tuple[str, str], ...] = ()
    name_regex: str | None = None
    search_queries: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()  # klíčová slova pro klasifikaci z textu webu / názvu
    economic_base: int = 50  # 0–100: typická schopnost investovat do webu
    visual_importance: int = 70  # 0–100: jak moc obor prodává přes vizuál
    typical_service: str = "redesign_small"
    nace_prefixes: tuple[str, ...] = field(default_factory=tuple)


SEGMENTS: list[Segment] = [
    # ---------------- Tier 1 ----------------
    Segment("interior_design", "Interiéroví designéři a studia", 1,
            osm_tags=(("shop", "interior_decoration"), ("craft", "interior_designer"), ("office", "interior_design")),
            name_regex="interi[eé]r|interior",
            search_queries=("interiérový design {city}", "interiérové studio {city}", "návrh interiéru {city}"),
            keywords=("interiér", "návrh interiéru", "interior design", "bytový design", "vizualizace"),
            economic_base=75, visual_importance=95, typical_service="rebranding_web", nace_prefixes=("7410",)),
    Segment("premium_florist", "Prémiová květinová studia", 1,
            osm_tags=(("shop", "florist"),),
            search_queries=("květinové studio {city}", "floristika {city}"),
            keywords=("floristika", "květin", "kytice", "florist", "aranžmá"),
            economic_base=45, visual_importance=95, typical_service="full_web", nace_prefixes=("4776",)),
    Segment("wedding_florist", "Svatební floristky", 1,
            name_regex="svatebn[ií].*(flor|kvet|květ)|wedding.*flor",
            search_queries=("svatební floristika {city}", "svatební výzdoba {city}"),
            keywords=("svatební floristika", "svatební kytice", "výzdoba svatby", "svatební výzdoba"),
            economic_base=50, visual_importance=95, typical_service="full_web"),
    Segment("wedding_agency", "Svatební agentury", 1,
            osm_tags=(("shop", "wedding"), ("office", "wedding_planner")),
            name_regex="svatb|wedding",
            search_queries=("svatební agentura {city}", "svatební koordinátorka {city}", "wedding planner {city}"),
            keywords=("svatební agentura", "svatební koordinátor", "wedding planner", "organizace svatby"),
            economic_base=65, visual_importance=95, typical_service="full_web", nace_prefixes=("9604", "8230")),
    Segment("beauty_studio", "Beauty studia", 1,
            osm_tags=(("shop", "beauty"), ("shop", "nails")),
            search_queries=("beauty studio {city}", "kosmetický salon {city}"),
            keywords=("beauty", "manikúra", "řasy", "obočí", "kosmetika", "líčení"),
            economic_base=45, visual_importance=85, typical_service="redesign_small", nace_prefixes=("9602",)),
    Segment("premium_cosmetics", "Prémiová kosmetická studia", 1,
            osm_tags=(("shop", "cosmetics"),),
            name_regex="kosmetick|cosmetic|skin|beauty clinic",
            search_queries=("kosmetické studio {city}", "ošetření pleti {city}"),
            keywords=("ošetření pleti", "kosmetické studio", "hydrafacial", "anti-age", "dermaplaning"),
            economic_base=55, visual_importance=85, typical_service="full_web", nace_prefixes=("9602",)),
    Segment("pilates_studio", "Pilates studia", 1,
            osm_tags=(("sport", "pilates"),),
            name_regex="pilates|reformer",
            search_queries=("pilates studio {city}", "reformer pilates {city}"),
            keywords=("pilates", "reformer", "barre"),
            economic_base=55, visual_importance=85, typical_service="full_web", nace_prefixes=("9313",)),
    Segment("fitness_studio", "Fitness studia", 1,
            osm_tags=(("leisure", "fitness_centre"),),
            search_queries=("fitness studio {city}", "boutique fitness {city}"),
            keywords=("fitness", "posilovna", "skupinové lekce", "kruhový trénink", "crossfit"),
            economic_base=55, visual_importance=75, typical_service="full_web", nace_prefixes=("9313",)),
    Segment("custom_carpentry", "Zakázkové truhlářství", 1,
            osm_tags=(("craft", "carpenter"), ("craft", "cabinet_maker"), ("craft", "joiner")),
            name_regex="truhl[aá]ř|nábytek na míru|nabytek na miru",
            search_queries=("truhlářství na míru {city}", "nábytek na míru {city}"),
            keywords=("truhlářství", "nábytek na míru", "masiv", "zakázková výroba", "vestavěné skříně"),
            economic_base=70, visual_importance=85, typical_service="full_web", nace_prefixes=("3109", "1623")),
    Segment("custom_kitchens", "Výrobci kuchyní na míru", 1,
            osm_tags=(("shop", "kitchen"),),
            name_regex="kuchyn|kuchyň|kitchen",
            search_queries=("kuchyně na míru {city}", "výroba kuchyní {city}"),
            keywords=("kuchyně na míru", "kuchyňské linky", "kuchyňské studio"),
            economic_base=80, visual_importance=90, typical_service="full_web", nace_prefixes=("3102",)),
    Segment("architecture_studio", "Menší architektonická studia", 1,
            osm_tags=(("office", "architect"),),
            name_regex="architekt|architect|ateli[eé]r",
            search_queries=("architektonický ateliér {city}", "architekt rodinné domy {city}"),
            keywords=("architekt", "architektonick", "projekce", "studie", "rodinný dům"),
            economic_base=75, visual_importance=95, typical_service="rebranding_web", nace_prefixes=("7111",)),
    Segment("design_brand", "Designové a lifestyle značky", 1,
            osm_tags=(("shop", "houseware"), ("shop", "gift"), ("shop", "interior_decoration")),
            name_regex="design|concept store|lifestyle",
            search_queries=("česká designová značka", "designový obchod {city}", "concept store {city}"),
            keywords=("designová značka", "ručně vyráběné", "lifestyle", "concept store", "česká značka"),
            economic_base=60, visual_importance=95, typical_service="eshop"),

    # ---------------- Tier 2 ----------------
    Segment("aesthetic_clinic", "Estetické kliniky", 2,
            osm_tags=(("healthcare:speciality", "plastic_surgery"), ("healthcare:speciality", "dermatology")),
            name_regex="estetick|aesthetic|plastick",
            search_queries=("estetická klinika {city}", "estetická medicína {city}"),
            keywords=("estetická medicína", "botox", "kyselina hyaluronová", "plastická chirurgie", "laser"),
            economic_base=85, visual_importance=85, typical_service="rebranding_web", nace_prefixes=("8622",)),
    Segment("premium_hair_salon", "Prémiové kadeřnické salony", 2,
            osm_tags=(("shop", "hairdresser"),),
            search_queries=("kadeřnictví {city}", "kadeřnický salon {city}"),
            keywords=("kadeřnictví", "balayage", "střih", "barvení", "barber"),
            economic_base=45, visual_importance=80, typical_service="redesign_small", nace_prefixes=("9602",)),
    Segment("photographer", "Fotografové", 2,
            osm_tags=(("craft", "photographer"), ("shop", "photo"), ("craft", "photographic_studio")),
            name_regex="foto|photo",
            search_queries=("fotograf {city}", "fotoateliér {city}"),
            keywords=("fotograf", "focení", "fotoateliér", "portrét"),
            economic_base=35, visual_importance=95, typical_service="redesign_small", nace_prefixes=("7420",)),
    Segment("wedding_photographer", "Svatební fotografové", 2,
            name_regex="svatebn[ií] foto|wedding photo",
            search_queries=("svatební fotograf {city}", "svatební video {city}"),
            keywords=("svatební fotograf", "svatební focení", "svatební video"),
            economic_base=45, visual_importance=95, typical_service="redesign_small", nace_prefixes=("7420",)),
    Segment("real_estate", "Realitní kanceláře", 2,
            osm_tags=(("office", "estate_agent"),),
            search_queries=("realitní kancelář {city}", "reality {city}"),
            keywords=("reality", "realitní", "prodej nemovitostí", "pronájem"),
            economic_base=75, visual_importance=75, typical_service="full_web", nace_prefixes=("6831",)),
    Segment("boutique_hotel", "Boutique hotely", 2,
            osm_tags=(("tourism", "hotel"),),
            search_queries=("boutique hotel {city}", "designový hotel {city}"),
            keywords=("hotel", "ubytování", "pokoje", "boutique", "snídaně"),
            economic_base=80, visual_importance=90, typical_service="rebranding_web", nace_prefixes=("5510",)),
    Segment("premium_guesthouse", "Prémiové penziony", 2,
            osm_tags=(("tourism", "guest_house"), ("tourism", "chalet")),
            search_queries=("penzion {city}", "apartmány {city}"),
            keywords=("penzion", "apartmán", "ubytování", "chata"),
            economic_base=55, visual_importance=90, typical_service="full_web", nace_prefixes=("5520",)),
    Segment("wellness_center", "Wellness centra", 2,
            osm_tags=(("leisure", "sauna"), ("shop", "massage"), ("amenity", "spa"), ("leisure", "spa")),
            name_regex="wellness|spa|masáž|masaz",
            search_queries=("wellness {city}", "masážní salon {city}"),
            keywords=("wellness", "sauna", "masáž", "relaxace", "spa"),
            economic_base=60, visual_importance=85, typical_service="full_web", nace_prefixes=("9604",)),
    Segment("car_dealer", "Autosalony", 2,
            osm_tags=(("shop", "car"),),
            search_queries=("autosalon {city}", "prodej vozů {city}"),
            keywords=("autosalon", "vozy", "prodej aut", "ojeté vozy", "operativní leasing"),
            economic_base=80, visual_importance=75, typical_service="full_web", nace_prefixes=("4511",)),
    Segment("auto_detailing", "Auto detailing", 2,
            name_regex="detailing|detail|keramick|car care",
            osm_tags=(("service:vehicle:detailing", "yes"),),
            search_queries=("auto detailing {city}", "keramická ochrana laku {city}"),
            keywords=("detailing", "keramická ochrana", "leštění", "tepování", "ppf"),
            economic_base=50, visual_importance=85, typical_service="redesign_small", nace_prefixes=("4520",)),
    Segment("event_agency", "Eventové agentury", 2,
            osm_tags=(("office", "event_management"),),
            name_regex="event|eventov",
            search_queries=("eventová agentura {city}", "firemní akce {city}"),
            keywords=("eventy", "firemní akce", "teambuilding", "event"),
            economic_base=70, visual_importance=85, typical_service="rebranding_web", nace_prefixes=("8230",)),
    Segment("construction_company", "Stavební společnosti", 2,
            osm_tags=(("craft", "builder"), ("office", "construction_company")),
            name_regex="stav|build",
            search_queries=("stavební firma rodinné domy {city}", "stavební společnost {city}"),
            keywords=("stavební", "výstavba", "rekonstrukce", "rodinné domy", "realizace staveb"),
            economic_base=80, visual_importance=60, typical_service="full_web", nace_prefixes=("4120", "4110")),

    # ---------------- Tier 3 ----------------
    Segment("personal_trainer", "Osobní trenéři", 3,
            name_regex="trenér|trener|personal training",
            search_queries=("osobní trenér {city}", "personal trainer {city}"),
            keywords=("osobní trenér", "trénink", "personal training"),
            economic_base=30, visual_importance=70, typical_service="redesign_small"),
    Segment("fitness_coach", "Fitness koučové", 3,
            search_queries=("fitness kouč online", "online koučink hubnutí"),
            keywords=("kouč", "koučink", "online trénink", "jídelníček"),
            economic_base=35, visual_importance=70, typical_service="redesign_small"),
    Segment("nutrition_advisor", "Výživoví poradci", 3,
            osm_tags=(("healthcare", "nutrition_counselling"),),
            search_queries=("výživový poradce {city}", "nutriční terapeut {city}"),
            keywords=("výživový poradce", "nutriční", "jídelníček", "výživa"),
            economic_base=30, visual_importance=60, typical_service="redesign_small"),
    Segment("consultant", "Profesionální konzultanti", 3,
            osm_tags=(("office", "consulting"),),
            search_queries=("poradenství pro firmy {city}", "konzultant {city}"),
            keywords=("poradenství", "konzultace", "konzultant"),
            economic_base=55, visual_importance=50, typical_service="full_web", nace_prefixes=("7022",)),
    Segment("small_eshop", "Menší e-shopy", 3,
            search_queries=("eshop ručně vyráběné", "česká značka eshop"),
            keywords=("e-shop", "košík", "doprava zdarma", "do košíku"),
            economic_base=55, visual_importance=80, typical_service="eshop", nace_prefixes=("4791",)),
    Segment("local_manufacturer", "Lokální výrobci", 3,
            osm_tags=(("craft", "confectionery"), ("craft", "brewery"), ("craft", "winery"), ("craft", "distillery"),
                      ("craft", "pottery"), ("craft", "jeweller")),
            search_queries=("lokální výrobce {city}", "manufaktura {city}"),
            keywords=("manufaktura", "ruční výroba", "lokální", "výrobce"),
            economic_base=50, visual_importance=75, typical_service="eshop"),
    Segment("fashion_brand", "Menší módní značky", 3,
            osm_tags=(("shop", "boutique"), ("shop", "clothes")),
            name_regex="atelier|ateliér|boutique|fashion|móda|moda",
            search_queries=("česká módní značka", "módní ateliér {city}"),
            keywords=("kolekce", "móda", "oblečení", "módní značka"),
            economic_base=50, visual_importance=95, typical_service="eshop", nace_prefixes=("1413",)),
    Segment("visual_services", "Další vizuálně orientované služby", 3,
            osm_tags=(("shop", "tattoo"), ("craft", "signmaker")),
            search_queries=("tetovací studio {city}",),
            keywords=("tetování", "grafika", "polep"),
            economic_base=40, visual_importance=80, typical_service="redesign_small"),
]

SEGMENT_BY_KEY: dict[str, Segment] = {s.key: s for s in SEGMENTS}

TIER_LABELS = {1: "Tier 1 — Nejvyšší priorita", 2: "Tier 2 — Vysoký potenciál", 3: "Tier 3 — Doplňkové"}

# Služby Project Two (pro Service Fit a odhad rozpočtu)
SERVICES = {
    "redesign_small": "Redesign menšího webu",
    "full_web": "Kompletní web",
    "rebranding_web": "Rebranding + web",
    "eshop": "E-shop",
    "new_web": "Nový web (firma web nemá)",
}


def get_segment(key: str | None) -> Segment | None:
    if not key:
        return None
    return SEGMENT_BY_KEY.get(key)


def classify_by_text(text: str, name: str = "") -> tuple[str | None, int]:
    """Odhadne segment podle textu webu / názvu. Vrací (klíč, počet shod)."""
    hay = f"{name} {text}".lower()
    best: tuple[str | None, int] = (None, 0)
    for seg in SEGMENTS:
        hits = sum(hay.count(k.lower()) for k in seg.keywords)
        if hits > best[1]:
            best = (seg.key, hits)
    return best
