"""Ohleduplný HTTP klient.

- respektuje robots.txt,
- omezuje rychlost dotazů na doménu,
- retry s exponenciálním čekáním (429 / 5xx / síťové chyby),
- omezuje velikost stahovaných dat,
- chrání proti SSRF (neotevírá privátní / lokální adresy).
"""
from __future__ import annotations

import ipaddress
import logging
import random
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, TypeVar
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T")


class FetchError(Exception):
    pass


class BlockedByPolicy(FetchError):
    """Přístup zakázán (robots.txt, privátní síť, nepovolené schéma)."""


class RateLimiter:
    """Jednoduchý thread-safe limiter: minimální rozestup mezi požadavky na klíč."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def wait(self, key: str, min_interval: float) -> None:
        if min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            allowed = self._next_allowed.get(key, now)
            wait_for = max(0.0, allowed - now)
            self._next_allowed[key] = max(now, allowed) + min_interval
        if wait_for > 0:
            time.sleep(wait_for)


RATE_LIMITER = RateLimiter()


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_on: tuple[type[BaseException], ...] = (httpx.TransportError,),
    should_retry: Callable[[BaseException], bool] | None = None,
) -> T:
    """Spustí fn s exponenciálním čekáním mezi pokusy (s jitterem)."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            if should_retry is not None and not should_retry(exc):
                raise
            last = exc
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2 ** i)) * (0.75 + random.random() * 0.5)
            log.info("Opakuji pokus %s/%s za %.1fs: %s", i + 2, attempts, delay, exc)
            time.sleep(delay)
    assert last is not None
    raise last


class RetryableStatus(Exception):
    def __init__(self, status: int, retry_after: float | None = None):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.retry_after = retry_after


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # DNS selhalo – necháme rozhodnout HTTP vrstvu (vrátí chybu spojení)
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    headers: dict
    text: str
    content: bytes
    elapsed_ms: int
    truncated: bool


class PoliteFetcher:
    def __init__(self, user_agent: str | None = None, timeout: float | None = None,
                 per_domain_delay: float | None = None) -> None:
        s = get_settings()
        self.user_agent = user_agent or s.user_agent
        self.timeout = timeout or s.http_timeout
        self.per_domain_delay = s.per_domain_delay_seconds if per_domain_delay is None else per_domain_delay
        self.max_bytes = s.max_page_bytes
        self.block_private = s.block_private_networks
        self._robots: dict[str, tuple[robotparser.RobotFileParser | None, float]] = {}
        self._robots_lock = threading.Lock()
        self.client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "cs,sk;q=0.9,en;q=0.7"},
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=5,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PoliteFetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    def check_url_allowed(self, url: str) -> None:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            raise BlockedByPolicy(f"Nepovolené schéma: {p.scheme}")
        if not p.hostname:
            raise BlockedByPolicy("Chybí hostname")
        if self.block_private and not _is_public_host(p.hostname):
            raise BlockedByPolicy(f"Adresa {p.hostname} směřuje do privátní sítě – blokováno")

    def robots_allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        with self._robots_lock:
            cached = self._robots.get(base)
        if cached and time.time() - cached[1] < 3600:
            rp = cached[0]
        else:
            rp = robotparser.RobotFileParser()
            try:
                self.check_url_allowed(base)
                RATE_LIMITER.wait(p.netloc, self.per_domain_delay)
                r = self.client.get(urljoin(base, "/robots.txt"), timeout=10)
                if r.status_code >= 400:
                    rp = None  # robots neexistuje -> povoleno
                else:
                    rp.parse(r.text.splitlines())
            except Exception:  # noqa: BLE001 - nedostupný robots.txt = povoleno
                rp = None
            with self._robots_lock:
                self._robots[base] = (rp, time.time())
        if rp is None:
            return True
        # RobotFileParser použije pravidla pro náš UA, jinak pravidla pro "*"
        return rp.can_fetch(self.user_agent, url)

    def get(self, url: str, *, respect_robots: bool = True, attempts: int = 3) -> FetchResult:
        self.check_url_allowed(url)
        if respect_robots and not self.robots_allowed(url):
            raise BlockedByPolicy(f"robots.txt nepovoluje přístup na {url}")
        host = urlparse(url).netloc

        def _do() -> FetchResult:
            RATE_LIMITER.wait(host, self.per_domain_delay)
            start = time.monotonic()
            with self.client.stream("GET", url) as r:
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("retry-after")
                    raise RetryableStatus(r.status_code, float(ra) if ra and ra.isdigit() else None)
                # kontrola finální adresy po přesměrování
                self.check_url_allowed(str(r.url))
                chunks: list[bytes] = []
                size = 0
                truncated = False
                for chunk in r.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > self.max_bytes:
                        truncated = True
                        break
                content = b"".join(chunks)
                encoding = r.encoding or "utf-8"
                try:
                    text = content.decode(encoding, errors="replace")
                except LookupError:
                    text = content.decode("utf-8", errors="replace")
                return FetchResult(
                    url=url, final_url=str(r.url), status_code=r.status_code, headers=dict(r.headers), text=text,
                    content=content, elapsed_ms=int((time.monotonic() - start) * 1000), truncated=truncated,
                )

        return with_retries(_do, attempts=attempts, base_delay=1.5,
                            retry_on=(httpx.TransportError, RetryableStatus))


def api_request(
    method: str,
    url: str,
    *,
    rate_key: str,
    min_interval: float,
    attempts: int = 4,
    timeout: float = 30.0,
    **kwargs,
) -> httpx.Response:
    """Volání veřejného API s rate limitingem a retry (pro konektory)."""
    s = get_settings()
    headers = {"User-Agent": s.user_agent, **kwargs.pop("headers", {})}

    def _do() -> httpx.Response:
        RATE_LIMITER.wait(rate_key, min_interval)
        r = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("retry-after")
            raise RetryableStatus(r.status_code, float(ra) if ra and ra.isdigit() else None)
        return r

    return with_retries(_do, attempts=attempts, base_delay=2.0, retry_on=(httpx.TransportError, RetryableStatus))
