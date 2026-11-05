"""Technický audit webu – objektivní, měřitelné metriky (ne estetika).

Výstup: technical_score 0–100 (vyšší = lepší) a seznam zjištěných problémů s důkazy.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _issue(code: str, title: str, detail: str, severity: str, penalty: float) -> dict[str, Any]:
    return {"code": code, "title": title, "detail": detail, "severity": severity, "penalty": penalty}


def technical_audit(extracted: dict[str, Any], browser: dict[str, Any] | None = None) -> dict[str, Any]:
    browser = browser or {}
    issues: list[dict[str, Any]] = []
    positives: list[str] = []
    year_now = date.today().year
    desk = browser.get("home_desktop") or {}
    mob = browser.get("home_mobile") or {}

    if not extracted.get("https"):
        issues.append(_issue("no_https", "Web neběží na HTTPS", "Prohlížeče označují web jako nezabezpečený.", "high", 12))
    else:
        positives.append("Web běží na HTTPS")
    if not extracted.get("has_viewport"):
        issues.append(_issue("no_viewport", "Chybí meta viewport", "Web pravděpodobně není responzivní (mobilní zobrazení).", "high", 15))
    if mob.get("horizontal_overflow"):
        issues.append(_issue("mobile_overflow", "Na mobilu se obsah nevejde na šířku",
                             "Stránka na mobilu vodorovně přetéká (nutnost posouvat do strany).", "high", 10))
    if mob.get("small_text_ratio") is not None and mob["small_text_ratio"] > 0.3:
        issues.append(_issue("mobile_small_text", "Malé písmo na mobilu",
                             f"{int(mob['small_text_ratio'] * 100)} % textu má na mobilu méně než 12 px.", "medium", 6))
    cy = extracted.get("copyright_year")
    if cy and cy <= year_now - 4:
        issues.append(_issue("old_copyright", f"Copyright z roku {cy}",
                             "Patička webu naznačuje, že web dlouho nikdo neaktualizoval.", "medium", 6))
    jq = extracted.get("jquery_version")
    if jq:
        try:
            major, minor = (int(x) for x in jq.split(".")[:2])
            if major < 2 or (major == 1 and minor < 9):
                issues.append(_issue("old_jquery", f"Zastaralá knihovna jQuery {jq}", "Indikuje starší technické řešení webu.", "low", 4))
        except ValueError:
            pass
    if extracted.get("bootstrap_major") and extracted["bootstrap_major"] <= 3:
        issues.append(_issue("old_bootstrap", f"Bootstrap {extracted['bootstrap_major']}", "Starší verze CSS frameworku (cca 2013–2018).", "low", 3))
    if "Flash" in (extracted.get("technologies") or []):
        issues.append(_issue("flash", "Web obsahuje Flash", "Flash už prohlížeče nepodporují.", "high", 15))
    if (extracted.get("deprecated_tags") or 0) > 0:
        issues.append(_issue("deprecated_html", "Zastaralé HTML značky",
                             f"Nalezeno {extracted['deprecated_tags']}× <font>/<center>/<marquee>/<frame>.", "medium", 6))
    if (extracted.get("layout_tables") or 0) > 0:
        issues.append(_issue("table_layout", "Rozvržení pomocí tabulek", "Typické pro weby z doby před rokem 2010.", "medium", 8))
    if not extracted.get("title"):
        issues.append(_issue("no_title", "Chybí titulek stránky", "Stránka nemá <title> – horší SEO i sdílení.", "medium", 4))
    if not extracted.get("meta_description"):
        issues.append(_issue("no_meta_description", "Chybí meta description", "Google zobrazí náhodný text z webu.", "low", 3))
    if not extracted.get("h1"):
        issues.append(_issue("no_h1", "Chybí hlavní nadpis (H1)", "Stránka nemá jasně označený hlavní nadpis.", "low", 2))
    if not extracted.get("has_og_image"):
        issues.append(_issue("no_og", "Chybí náhledový obrázek pro sdílení", "Při sdílení na sociálních sítích se nezobrazí kvalitní náhled.", "low", 2))
    imgs = extracted.get("image_count") or 0
    if imgs and (extracted.get("images_without_alt") or 0) / imgs > 0.6:
        issues.append(_issue("img_alt", "Obrázky bez popisků", f"{extracted['images_without_alt']} z {imgs} obrázků nemá alt text.", "low", 2))
    load = desk.get("load_ms") or desk.get("wall_load_ms")
    if load and load > 6000:
        issues.append(_issue("slow", "Pomalé načítání", f"Úvodní stránka se načítala {load / 1000:.1f} s.", "medium", 8))
    elif load and load > 3500:
        issues.append(_issue("slowish", "Delší načítání", f"Úvodní stránka se načítala {load / 1000:.1f} s.", "low", 4))
    elif load:
        positives.append(f"Rychlé načítání ({load / 1000:.1f} s)")
    tkb = desk.get("transfer_kb")
    if tkb and tkb > 6000:
        issues.append(_issue("heavy", "Velmi těžká stránka", f"Přenos přes {tkb / 1024:.1f} MB.", "low", 3))
    if (desk.get("broken_images") or 0) > 0:
        issues.append(_issue("broken_images", "Nefunkční obrázky", f"{desk['broken_images']} obrázků se nenačetlo.", "medium", 5))
    if (desk.get("lowres_images") or 0) >= 3:
        issues.append(_issue("lowres_images", "Obrázky v nízkém rozlišení", f"{desk['lowres_images']} obrázků je roztaženo nad své rozlišení.", "medium", 4))
    if desk and desk.get("above_fold_ctas", 0) == 0:
        issues.append(_issue("no_cta", "Chybí výzva k akci v první obrazovce",
                             "Na první obrazovce není viditelné tlačítko typu Kontakt / Objednat / Rezervovat.", "medium", 5))
    if (desk.get("font_family_count") or 0) > 5:
        issues.append(_issue("many_fonts", "Mnoho různých písem", f"Použito {desk['font_family_count']} rodin písma.", "low", 3))
    if (desk.get("console_errors") or 0) >= 5:
        issues.append(_issue("js_errors", "Chyby JavaScriptu", f"{desk['console_errors']} chyb v konzoli prohlížeče.", "low", 2))
    if not extracted.get("has_contact_form") and not extracted.get("has_booking") and not extracted.get("emails"):
        issues.append(_issue("hard_to_contact", "Obtížný kontakt", "Na webu jsme nenašli formulář, rezervaci ani e-mail.", "medium", 5))
    if extracted.get("uses_site_builder"):
        issues.append(_issue("site_builder", f"Web postavený na {extracted.get('cms')}",
                             "Šablonový builder – omezené možnosti designu a výkonu.", "low", 3))
    if (extracted.get("total_word_count") or 0) < 150:
        issues.append(_issue("thin_content", "Velmi málo obsahu", "Web obsahuje minimum textu o službách.", "medium", 5))
    if not any(t in (extracted.get("technologies") or []) for t in ("Google Analytics", "Google Tag Manager")):
        issues.append(_issue("no_analytics", "Bez měření návštěvnosti", "Nenalezeno Google Analytics / GTM.", "low", 2))

    penalty = sum(i["penalty"] for i in issues)
    score = max(0.0, min(100.0, 100.0 - penalty))
    measured = sum(1 for x in (desk, mob) if x)
    return {
        "technical_score": round(score, 1),
        "issues": sorted(issues, key=lambda i: -i["penalty"]),
        "positives": positives,
        "browser_measured": measured > 0,
    }
