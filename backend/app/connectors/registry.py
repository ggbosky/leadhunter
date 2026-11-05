"""Registr konektorů a synchronizace evidence zdrojů do DB."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSource, utcnow
from .ares import AresConnector
from .base import Connector
from .overpass import OverpassConnector
from .search_api import BraveSearchConnector, GoogleCseConnector, ManualConnector, WebsiteConnector

_CONNECTORS: dict[str, Connector] | None = None


def connectors() -> dict[str, Connector]:
    global _CONNECTORS
    if _CONNECTORS is None:
        items: list[Connector] = [OverpassConnector(), AresConnector(), BraveSearchConnector(), GoogleCseConnector(),
                                  WebsiteConnector(), ManualConnector()]
        _CONNECTORS = {c.key: c for c in items}
    return _CONNECTORS


def get_connector(key: str) -> Connector:
    return connectors()[key]


def ensure_data_sources(db: Session) -> dict[str, DataSource]:
    existing = {ds.key: ds for ds in db.scalars(select(DataSource))}
    for key, c in connectors().items():
        ds = existing.get(key)
        if ds is None:
            ds = DataSource(key=key, name=c.name, kind=c.kind, base_url=c.base_url or None,
                            access_policy=c.access_policy, rate_limit_per_minute=c.rate_limit_per_minute,
                            enabled=True)
            db.add(ds)
            existing[key] = ds
        else:
            ds.name, ds.kind, ds.access_policy = c.name, c.kind, c.access_policy
            ds.rate_limit_per_minute = c.rate_limit_per_minute
    db.flush()
    return existing


def check_all(db: Session) -> list[dict]:
    sources = ensure_data_sources(db)
    out = []
    for key, c in connectors().items():
        res = c.check_availability()
        ds = sources[key]
        ds.last_check_at = utcnow()
        ds.last_status = res.status
        ds.last_error = None if res.status == "ok" else res.detail
        out.append({**c.describe(), "status": res.status, "detail": res.detail, "enabled": ds.enabled})
    db.flush()
    return out


def record_usage(db: Session, key: str, *, requests: int = 0, errors: int = 0, records: int = 0,
                 error: str | None = None) -> None:
    ds = db.scalar(select(DataSource).where(DataSource.key == key))
    if ds is None:
        return
    ds.total_requests += requests
    ds.total_errors += errors
    ds.total_records += records
    if error:
        ds.last_error = error[:2000]
        ds.last_status = "error"
    elif requests:
        ds.last_status = "ok"
    ds.last_check_at = datetime.utcnow()
