from app.services.normalize import (
    is_non_company_domain,
    is_valid_ico,
    normalize_address,
    normalize_domain,
    normalize_ico,
    normalize_linkedin,
    normalize_name,
    normalize_phone,
)


def test_domain_normalization():
    assert normalize_domain("https://www.Example.cz/kontakt?x=1") == "example.cz"
    assert normalize_domain("example.cz") == "example.cz"
    assert normalize_domain("http://shop.example.co.uk/") == "example.co.uk"
    # sdílené platformy – identitu určuje subdoména
    assert normalize_domain("https://kvetiny-jana.webnode.cz/") == "kvetiny-jana.webnode.cz"
    assert normalize_domain("https://janinka.wixsite.com/kvetiny") == "janinka.wixsite.com/kvetiny"
    assert normalize_domain("") is None


def test_non_company_domains():
    assert is_non_company_domain("https://www.facebook.com/firma")
    assert is_non_company_domain("https://www.firmy.cz/detail/123")
    assert not is_non_company_domain("https://bozikytky.cz")


def test_name_normalization_strips_legal_form():
    assert normalize_name("Kuchyně Novák, s.r.o.") == "kuchyne novak"
    assert normalize_name("KUCHYNĚ NOVÁK spol. s r.o.") == "kuchyne novak"
    assert normalize_name("Studio & Co a.s.") == "studio a co"


def test_ico_checksum():
    assert is_valid_ico("27074358")
    assert not is_valid_ico("27074359")
    assert normalize_ico("IČO: 270 74 358") == "27074358"
    assert normalize_ico("6947") == "00006947"


def test_phone_and_linkedin():
    assert normalize_phone("723 528 088") == "+420723528088"
    assert normalize_phone("00421 900 123 456") == "+421900123456"
    assert normalize_linkedin("linkedin.com/in/Jana-Novakova/") == "https://www.linkedin.com/in/jana-novakova"
    assert normalize_linkedin("https://example.com") is None


def test_address():
    assert normalize_address("Náměstí Míru 12", "Brno", "602 00") == normalize_address("nám. Míru 12", "Brno", "602 00")
    assert normalize_address(None, "Brno", None) is None
