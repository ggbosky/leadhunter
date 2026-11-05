from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Query

from ..config import get_settings


def require_token(authorization: str | None = Header(default=None), token: str | None = Query(default=None)) -> None:
    expected = get_settings().api_token
    if not expected:
        return
    supplied = None
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    elif token:
        supplied = token
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Neplatný nebo chybějící API token")
