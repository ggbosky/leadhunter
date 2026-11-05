from app.services.site_crawler import discover_pages, extract_page, merge_extracted
from app.services.technical_audit import technical_audit
from bs4 import BeautifulSoup

OLD_SITE = """<html><head><title>Truhlářství Dřevo Novák</title>
<script src="/js/jquery-1.4.2.min.js"></script></head>
<body><table><tr><td><table><tr><td><font color=red>Vítejte</font></td></tr></table></td></tr></table>
<center><h2>Nábytek na míru</h2></center>
<a href="/realizace.html">Naše realizace</a> <a href="/kontakt.php">Kontakt</a> <a href="/sluzby/">Služby</a>
<a href="https://www.facebook.com/drevonovak">Facebook</a> <a href="mailto:info@drevonovak.cz">napište</a>
<p>Jsme rodinná firma, fungujeme od roku 1998. Vyrábíme kuchyně a nábytek na míru z masivu.
Hledáme nového truhláře do týmu. Otevřeli jsme nový showroom v Brně.
Ceny kuchyní od 120 000 Kč. IČO: 27074358. Tel: 723 528 088. Majitel: Jan Novák</p>
<p>&copy; 2012 Dřevo Novák</p></body></html>"""


def test_extract_old_site():
    ex = extract_page(OLD_SITE, "http://drevonovak.cz/")
    assert ex["has_viewport"] is False
    assert ex["jquery_version"] == "1.4"
    assert ex["copyright_years"] == [2012]
    assert "27074358" in ex["icos"]
    assert "info@drevonovak.cz" in ex["emails"]
    assert "+420723528088" in ex["phones"]
    assert ex["socials"]["facebook"].startswith("https://www.facebook.com/drevonovak")
    assert ex["layout_tables"] >= 1 and ex["deprecated_tags"] >= 2
    assert "hiring" in ex["text_signals"] and "new_branch" in ex["text_signals"]
    assert 120000 in ex["prices"]
    assert ex["since_years"] == [1998]
    assert any(p["name"] == "Jan Novák" for p in ex["persons"])


def test_discover_pages():
    pages = discover_pages(BeautifulSoup(OLD_SITE, "lxml"), "http://drevonovak.cz/")
    assert pages["portfolio"].endswith("/realizace.html")
    assert pages["contact"].endswith("/kontakt.php")
    assert pages["services"].endswith("/sluzby/")


def test_technical_audit_flags_old_site():
    ex = merge_extracted({"home": extract_page(OLD_SITE, "http://drevonovak.cz/")})
    ex["https"] = False
    audit = technical_audit(ex, {})
    codes = {i["code"] for i in audit["issues"]}
    assert {"no_https", "no_viewport", "old_copyright", "old_jquery", "table_layout", "deprecated_html"} <= codes
    assert audit["technical_score"] < 50
