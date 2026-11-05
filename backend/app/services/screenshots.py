"""Pořizování screenshotů přes Playwright + měření v prohlížeči.

Ochrana cizích webů: max. 5 stránek na web, timeouty, blokace těžkých médií (video),
žádné odesílání formulářů. Kliká se maximálně na tlačítko souhlasu s cookies, aby
screenshot ukazoval skutečný vzhled webu.
"""
from __future__ import annotations

import glob
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import get_settings
from .http_client import RATE_LIMITER, PoliteFetcher

log = logging.getLogger(__name__)

DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
MOBILE = {
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/17.5 Mobile/15E148 Safari/604.1 ProjectTwoLeadHunter/1.0",
}
COOKIE_BUTTON_TEXTS = ["Přijmout vše", "Přijmout všechny", "Povolit vše", "Souhlasím", "Rozumím", "Přijmout",
                       "Accept all", "Accept", "Allow all", "I agree", "OK", "Prijať všetko", "Súhlasím"]

PAGE_METRICS_JS = r"""
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const doc = document.documentElement;
  const nav = performance.getEntriesByType('navigation')[0];
  const fonts = new Set(); const sizes = [];
  const els = Array.from(document.querySelectorAll('body *')).slice(0, 1500);
  for (const el of els) {
    const cs = getComputedStyle(el);
    if (el.childNodes.length && Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 2)) {
      fonts.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim().toLowerCase());
      sizes.push(parseFloat(cs.fontSize));
    }
  }
  const imgs = Array.from(document.images);
  const broken = imgs.filter(i => i.complete && i.naturalWidth === 0 && i.src).length;
  const lowres = imgs.filter(i => i.naturalWidth > 0 && i.clientWidth > 0 && i.naturalWidth < i.clientWidth * 0.75).length;
  const ctaRe = /(kontakt|objedn|rezerv|poptáv|poptav|napište|napiste|zavolejte|domluv|konzultac|nezávazn|book|contact|order|shop|nakup|koupit|termín)/i;
  const ctas = Array.from(document.querySelectorAll('a, button')).filter(el => {
    const r = el.getBoundingClientRect();
    return r.top < vh && r.bottom > 0 && r.width > 40 && r.height > 20 && ctaRe.test(el.innerText || '');
  }).length;
  const heroImg = Array.from(document.querySelectorAll('img, video, [style*="background"]')).some(el => {
    const r = el.getBoundingClientRect(); return r.top < vh * 0.8 && r.width > vw * 0.5 && r.height > vh * 0.3;
  });
  sizes.sort((a, b) => a - b);
  const median = sizes.length ? sizes[Math.floor(sizes.length / 2)] : null;
  const small = sizes.filter(s => s < 12).length;
  return {
    load_ms: nav ? Math.round(nav.loadEventEnd || nav.domContentLoadedEventEnd || 0) : null,
    dom_ms: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
    transfer_kb: nav ? Math.round((nav.transferSize || 0) / 1024) : null,
    page_height: doc.scrollHeight,
    horizontal_overflow: doc.scrollWidth > vw + 5,
    font_families: Array.from(fonts).slice(0, 12),
    font_family_count: fonts.size,
    median_font_px: median,
    small_text_ratio: sizes.length ? +(small / sizes.length).toFixed(2) : null,
    image_count: imgs.length,
    broken_images: broken,
    lowres_images: lowres,
    above_fold_ctas: ctas,
    hero_visual: heroImg,
    resource_count: performance.getEntriesByType('resource').length,
  };
}
"""


@dataclass
class ShotResult:
    screenshots: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    available: bool = True


_EXEC_CACHE: dict[str, str | None] = {}


def resolve_executable() -> str | None:
    """Najde spustitelný Chromium (nastavení -> výchozí Playwright -> lokální instalace)."""
    if "path" in _EXEC_CACHE:
        return _EXEC_CACHE["path"]
    s = get_settings()
    if s.playwright_executable_path:
        _EXEC_CACHE["path"] = s.playwright_executable_path
        return s.playwright_executable_path
    candidates: list[str] = []
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers", os.path.expanduser("~/.cache/ms-playwright")]
    for root in [r for r in roots if r]:
        candidates += sorted(glob.glob(f"{root}/chromium-*/chrome-linux*/chrome"), reverse=True)
        candidates += sorted(glob.glob(f"{root}/chromium_headless_shell-*/chrome-*/chrome-headless-shell"), reverse=True)
        candidates += sorted(glob.glob(f"{root}/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"), reverse=True)
    _EXEC_CACHE["path"] = None
    for c in candidates:
        if os.path.exists(c):
            _EXEC_CACHE["path"] = c
            break
    return _EXEC_CACHE["path"]


def _launch(p):
    try:
        return p.chromium.launch(args=["--disable-dev-shm-usage"])
    except Exception:  # noqa: BLE001
        exe = resolve_executable()
        if not exe:
            raise
        return p.chromium.launch(executable_path=exe, args=["--disable-dev-shm-usage", "--no-sandbox"])


def playwright_available() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Balíček playwright není nainstalován"
    try:
        with sync_playwright() as p:
            b = _launch(p)
            v = b.version
            b.close()
        return True, f"Chromium {v}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Prohlížeč nelze spustit: {str(exc)[:200]}"


def _dismiss_cookies(page) -> None:
    for text in COOKIE_BUTTON_TEXTS:
        try:
            btn = page.get_by_role("button", name=text, exact=True)
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=1500)
                page.wait_for_timeout(400)
                return
        except Exception:  # noqa: BLE001
            continue


def _block_heavy(route) -> None:
    if route.request.resource_type in ("media",):
        return route.abort()
    return route.continue_()


def capture_site(company_id: int, pages: dict[str, str], fetcher: PoliteFetcher | None = None) -> ShotResult:
    """pages: {"home": url, "services": url, "portfolio": url, "contact": url}"""
    s = get_settings()
    result = ShotResult()
    try:
        from playwright.sync_api import TimeoutError as PwTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        result.available = False
        result.errors.append("Playwright není nainstalován")
        return result
    out_dir = s.screenshot_dir / str(company_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    plan: list[tuple[str, str, dict]] = []
    if pages.get("home"):
        plan.append(("home", "desktop", DESKTOP))
        plan.append(("home", "mobile", MOBILE))
    for kind in ("services", "portfolio", "contact"):
        if pages.get(kind):
            plan.append((kind, "desktop", DESKTOP))
    plan = plan[: max(1, s.max_pages_per_site)]
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            try:
                for kind, device, profile in plan:
                    url = pages[kind]
                    if fetcher is not None and not fetcher.robots_allowed(url):
                        result.errors.append(f"{kind}: robots.txt nepovoluje")
                        continue
                    ctx_args = {k: v for k, v in profile.items()}
                    ctx_args.setdefault("user_agent", s.user_agent)
                    ctx_args["locale"] = "cs-CZ"
                    ctx = browser.new_context(**ctx_args, java_script_enabled=True, ignore_https_errors=True)
                    page = ctx.new_page()
                    console_errors: list[str] = []
                    page.on("console", lambda m: console_errors.append(m.text[:200]) if m.type == "error" else None)
                    page.route("**/*", _block_heavy)
                    try:
                        from urllib.parse import urlparse
                        RATE_LIMITER.wait(urlparse(url).netloc, s.per_domain_delay_seconds)
                        t0 = time.monotonic()
                        resp = page.goto(url, wait_until="domcontentloaded", timeout=s.screenshot_timeout_ms)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except PwTimeout:
                            pass
                        _dismiss_cookies(page)
                        page.wait_for_timeout(800)
                        # přirozené načtení lazy obrázků
                        page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 2500))")
                        page.wait_for_timeout(500)
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_timeout(300)
                        metrics = page.evaluate(PAGE_METRICS_JS)
                        metrics["wall_load_ms"] = int((time.monotonic() - t0) * 1000)
                        metrics["status"] = resp.status if resp else None
                        metrics["console_errors"] = len(console_errors)
                        height = min(int(metrics.get("page_height") or 900), s.screenshot_max_height if device == "desktop" else 3500)
                        fname = f"{stamp}_{kind}_{device}.jpg"
                        path = out_dir / fname
                        vw = profile["viewport"]["width"]
                        page.screenshot(path=str(path), type="jpeg", quality=72, full_page=True,
                                        clip={"x": 0, "y": 0, "width": vw, "height": max(height, profile["viewport"]["height"])})
                        fold = out_dir / f"{stamp}_{kind}_{device}_fold.jpg"
                        page.screenshot(path=str(fold), type="jpeg", quality=78, full_page=False)
                        result.screenshots.append({
                            "page": kind, "device": device, "url": url,
                            "path": str(path.relative_to(s.screenshot_dir)),
                            "fold_path": str(fold.relative_to(s.screenshot_dir)),
                        })
                        result.metrics[f"{kind}_{device}"] = metrics
                    except Exception as exc:  # noqa: BLE001
                        result.errors.append(f"{kind}/{device}: {type(exc).__name__}: {str(exc)[:200]}")
                    finally:
                        ctx.close()
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        result.available = False
        result.errors.append(f"Prohlížeč nelze spustit: {str(exc)[:300]}")
    # barevná paleta (objektivní měření ze screenshotu)
    for shot in result.screenshots:
        if shot["page"] == "home" and shot["device"] == "desktop":
            result.metrics["palette"] = palette_stats(s.screenshot_dir / shot["fold_path"])
    return result


def palette_stats(path: Path) -> dict[str, Any] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((320, 320))
        q = img.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: 12 * 3]
        counts = sorted(q.getcolors(), reverse=True)
        total = sum(c for c, _ in counts)
        colors = []
        for c, idx in counts[:8]:
            r, g, b = pal[idx * 3: idx * 3 + 3]
            colors.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(c / total, 3)})
        significant = sum(1 for c in colors if c["share"] >= 0.03)
        gray = img.convert("L")
        hist = gray.histogram()
        n = sum(hist)
        mean = sum(i * h for i, h in enumerate(hist)) / n
        var = sum(((i - mean) ** 2) * h for i, h in enumerate(hist)) / n
        return {"dominant": colors, "significant_colors": significant, "luminance_contrast": round(var ** 0.5, 1)}
    except Exception:  # noqa: BLE001
        return None
