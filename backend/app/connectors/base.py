"""Jednotné rozhraní konektorů pro zdroje firemních dat."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class DiscoveryQuery:
    segment_key: str | None = None
    region_code: str | None = None
    city: str | None = None
    country: str = "CZ"
    limit: int = 50
    require_website: bool = False
    keyword: str | None = None


@dataclass
class RawCompany:
    """Jednotný výstup všech konektorů."""

    source_key: str
    external_id: str
    name: str
    segment_key: str | None = None
    country: str = "CZ"
    region_code: str | None = None
    city: str | None = None
    street: str | None = None
    postcode: str | None = None
    lat: float | None = None
    lon: float | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    ico: str | None = None
    legal_form: str | None = None
    founded_on: str | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    opening_hours: str | None = None
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AvailabilityResult:
    status: str  # ok | unavailable | not_configured | error
    detail: str = ""


class ConnectorError(Exception):
    pass


class Connector(ABC):
    key: str = ""
    name: str = ""
    kind: str = "map"
    base_url: str = ""
    access_policy: str = ""
    rate_limit_per_minute: int = 10
    supports_discovery: bool = True

    @property
    def min_interval(self) -> float:
        return 60.0 / max(1, self.rate_limit_per_minute)

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    def check_availability(self) -> AvailabilityResult: ...

    def search(self, query: DiscoveryQuery) -> Iterator[RawCompany]:  # pragma: no cover - default
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "access_policy": self.access_policy,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "configured": self.is_configured(),
            "supports_discovery": self.supports_discovery,
        }
