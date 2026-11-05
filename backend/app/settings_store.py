"""Uživatelsky upravitelné nastavení ukládané v databázi (tabulka app_settings)."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from .models import AppSetting
from .regions import REGIONS
from .segments import SEGMENTS

DEFAULTS: dict[str, Any] = {
    "automation": {
        "paused": False,
        "daily_run_hour": 6,
        "daily_run_minute": 30,
        "timezone": "Europe/Prague",
        "daily_discovery_target": 100,
        "daily_analysis_target": 30,
        "daily_message_target": 10,
        "min_score_for_messages": 60,
        "reanalyze_after_days": 60,
    },
    "scoring": {
        "weights": {
            "design_gap": 0.30,
            "commercial_potential": 0.25,
            "buying_readiness": 0.20,
            "service_fit": 0.15,
            "contactability": 0.10,
        },
        "min_known_weight": 0.55,
        "already_good_visual_score": 80,
        "low_commercial_threshold": 25,
    },
    "pricing": {
        "redesign_small": {"label": "Redesign menšího webu", "min": 15000, "max": 30000},
        "full_web": {"label": "Kompletní web", "min": 25000, "max": 60000},
        "rebranding_web": {"label": "Rebranding + web", "min": 40000, "max": 100000},
        "eshop": {"label": "E-shop", "min": 40000, "max": None},
        "new_web": {"label": "Nový web", "min": 25000, "max": 60000},
    },
    # multiplikátor priority segmentu (1.0 = výchozí); může upravit uživatel nebo learning
    "segment_priorities": {s.key: {"enabled": True, "multiplier": 1.0} for s in SEGMENTS},
    "region_priorities": {r.code: {"enabled": r.country == "CZ", "priority": r.default_priority} for r in REGIONS},
    "followup": {
        "first_followup_days": 4,
        "second_followup_days": 7,
        "max_followups": 2,
        "connection_check_days": 5,
    },
    "messages": {
        "connection_request_max_chars": 280,
        "first_message_max_chars": 900,
        "default_strategy": "auto",
        "sender_name": "",
        "sender_role": "Project Two",
    },
    "agency": {
        "name": "Project Two",
        "url": "https://projectwo.com/",
        "facts": [
            "Web je venku za 2–3 týdny od zadání.",
            "Klient komunikuje přímo s tím, kdo web navrhuje a staví – bez account managerů.",
            "Nabídka a první rada zdarma, bez prezentací a bez závazku.",
            "Weby ladíme nejdřív pro mobil.",
        ],
        "portfolio": [
            {"name": "Boží kytky", "url": "https://bozikytky.cz", "segment": "premium_florist"},
            {"name": "Finelia", "url": "https://finelia.cz", "segment": "consultant"},
            {"name": "ALDA", "url": "https://aldastrih.cz", "segment": "photographer"},
            {"name": "Karel Drexler", "url": "https://drexler.digital", "segment": "design_brand"},
        ],
    },
}


def _merge(default: Any, stored: Any) -> Any:
    if isinstance(default, dict) and isinstance(stored, dict):
        out = copy.deepcopy(default)
        for k, v in stored.items():
            out[k] = _merge(default.get(k), v) if k in default else v
        return out
    return copy.deepcopy(stored) if stored is not None else copy.deepcopy(default)


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    default = DEFAULTS.get(key)
    if row is None:
        return copy.deepcopy(default)
    return _merge(default, row.value)


def set_setting(db: Session, key: str, value: Any) -> Any:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.flush()
    return get_setting(db, key)


def update_setting(db: Session, key: str, patch: dict) -> Any:
    current = get_setting(db, key)
    merged = _merge(current, patch)
    return set_setting(db, key, merged)


def all_settings(db: Session) -> dict[str, Any]:
    return {k: get_setting(db, k) for k in DEFAULTS}
