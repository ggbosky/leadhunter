from types import SimpleNamespace

from app.services import website_lookup as wl
from app.services.http_client import FetchResult


def _company(**kw):
    base = dict(name="Truhlářství Hanuš s.r.o.", ico="05049181", city="Břeclav", country="CZ",
                contacts=[SimpleNamespace(name="Jiří Hanuš", source="ares_vr")])
    base.update(kw)
    return SimpleNamespace(**base)


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, attempts=1, respect_robots=True):
        self.calls.append(url)
        if url not in self.pages:
            raise ConnectionError("nedostupné")
        html = self.pages[url]
        return FetchResult(url, url, 200, {}, html, html.encode(), 10, False)


def test_domain_candidates():
    c = wl.domain_candidates("Truhlářství Hanuš s.r.o.")
    assert "truhlarstvihanus.cz" in c and "truhlarstvi-hanus.cz" in c


def test_verify_by_person_with_http_fallback():
    html = "<html><head><title>Truhlářství Hanuš</title></head><body>Tel. 774 027 357 - Jiří Hanuš</body></html>"
    f = FakeFetcher({"http://truhlarstvihanus.cz/": html})
    method, ev, final = wl.verify_site("https://truhlarstvihanus.cz/", _company(), f)
    assert method == "name_person" and final == "http://truhlarstvihanus.cz/"


def test_verify_by_ico_and_reject_other_ico():
    ok = "<html><head><title>Cokoliv</title></head><body>IČO: 05049181</body></html>"
    method, _, _ = wl.verify_site("https://a.cz/", _company(), FakeFetcher({"https://a.cz/": ok}))
    assert method == "ico"
    other = "<html><head><title>Truhlářství Hanuš</title></head><body>Jiří Hanuš, IČO: 27074358</body></html>"
    method, why, _ = wl.verify_site("https://b.cz/", _company(), FakeFetcher({"https://b.cz/": other}))
    assert method is None and "jiné IČO" in why


def test_reject_generic_name_and_bot_challenge():
    generic = "<html><head><title>Květinářství</title></head><body>Brno</body></html>"
    c = _company(name="Květinářství", ico=None, city="Brno", contacts=[])
    method, _, _ = wl.verify_site("https://k.cz/", c, FakeFetcher({"https://k.cz/": generic}))
    assert method is None
    bot = "<html><body>Please wait... Verifying your browser</body></html>"
    method, why, _ = wl.verify_site("https://x.cz/", _company(), FakeFetcher({"https://x.cz/": bot}))
    assert method is None and "robot" in why
