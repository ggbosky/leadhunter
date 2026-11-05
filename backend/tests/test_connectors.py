from app.connectors.base import DiscoveryQuery
from app.connectors.overpass import build_query, element_to_raw
from app.connectors.search_api import clean_title, result_to_raw
from app.segments import get_segment


def test_overpass_query_region_and_city():
    q = build_query(get_segment("premium_florist"), DiscoveryQuery(segment_key="premium_florist", region_code="CZ-64"), 100)
    assert 'area["ISO3166-2"="CZ-64"]->.a;' in q
    assert 'nwr["shop"="florist"]["name"](area.a);' in q
    assert q.strip().endswith("out center tags 100;")
    q2 = build_query(get_segment("interior_design"), DiscoveryQuery(segment_key="interior_design", city="Wien", country="AT"), 50)
    assert 'area["ISO3166-1"="AT"][admin_level=2]->.c;' in q2 and '["name"="Wien"]' in q2 and "map_to_area->.a;" in q2
    assert 'nwr["name"~"interi[eé]r|interior",i]["shop"](area.a);' in q2


def test_overpass_element_parsing_and_chain_filter():
    el = {"type": "node", "id": 123, "lat": 49.19, "lon": 16.6, "tags": {
        "name": "Květinářství Lilie", "shop": "florist", "website": "https://lilie-kvetiny.cz", "addr:street": "Údolní",
        "addr:housenumber": "12", "addr:city": "Brno", "addr:postcode": "602 00", "phone": "+420 777 123 456",
        "contact:instagram": "https://instagram.com/lilie"}}
    raw = element_to_raw(el, None, "CZ")
    assert raw.segment_key == "premium_florist" and raw.region_code == "CZ-64"
    assert raw.street == "Údolní 12" and raw.social_links["instagram"].startswith("https://instagram.com")
    assert raw.external_id == "node/123"
    chain = {"type": "node", "id": 9, "tags": {"name": "Flora Chain", "shop": "florist", "brand:wikidata": "Q1"}}
    assert element_to_raw(chain, None, "CZ") is None


def test_search_result_filtering():
    q = DiscoveryQuery(segment_key="interior_design", city="Brno")
    assert result_to_raw("brave", "Firmy.cz – interiéry Brno", "https://www.firmy.cz/x", "", q) is None
    assert result_to_raw("brave", "Studio", "https://www.instagram.com/studio", "", q) is None
    r = result_to_raw("brave", "Interiérové studio Lumen | Návrhy interiérů Brno", "https://www.studio-lumen.cz/sluzby", "", q)
    assert r.website == "https://www.studio-lumen.cz/" and r.external_id == "studio-lumen.cz"
    assert clean_title("Úvod - Studio Lumen") == "Studio Lumen"
