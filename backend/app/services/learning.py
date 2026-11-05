"""Učení z výsledků – výkonnost segmentů a strategií zpráv.

Používá Bayesovské vyhlazení (beta prior), aby pár náhodných výsledků
nepřevrátilo priority. Návrhy úprav lze aplikovat ručně nebo automaticky.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, OutreachMessage
from ..segments import SEGMENTS
from ..settings_store import get_setting, set_setting
from .messages import STRATEGIES

POSITIVE = {"replied_positive", "meeting", "won"}
REPLIED = POSITIVE | {"replied_neutral", "replied_negative"}
PRIOR_SENT = 10
PRIOR_REPLY_RATE = 0.15
PRIOR_POSITIVE_RATE = 0.05


def _rates(sent: int, replied: int, positive: int) -> tuple[float, float, float]:
    rr = (replied + PRIOR_REPLY_RATE * PRIOR_SENT) / (sent + PRIOR_SENT)
    pr = (positive + PRIOR_POSITIVE_RATE * PRIOR_SENT) / (sent + PRIOR_SENT)
    return rr, pr, 0.4 * rr + 0.6 * pr * 3  # kladné odpovědi mají vyšší váhu


def strategy_performance(db: Session) -> dict[str, dict[str, Any]]:
    stats = {k: {"label": v, "sent": 0, "replied": 0, "positive": 0} for k, v in STRATEGIES.items()}
    rows = db.execute(select(OutreachMessage.strategy, OutreachMessage.outcome).where(
        OutreachMessage.status == "sent", OutreachMessage.message_type.in_(["first_message", "alternative", "connection_request"]))).all()
    for strategy, outcome in rows:
        if strategy not in stats:
            continue
        stats[strategy]["sent"] += 1
        if outcome in REPLIED:
            stats[strategy]["replied"] += 1
        if outcome in POSITIVE:
            stats[strategy]["positive"] += 1
    for k, s in stats.items():
        rr, pr, score = _rates(s["sent"], s["replied"], s["positive"])
        s.update(reply_rate=round(rr, 3), positive_rate=round(pr, 3), score=round(score, 4),
                 raw_reply_rate=round(s["replied"] / s["sent"], 3) if s["sent"] else None)
    return stats


def segment_performance(db: Session) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"sent": 0, "replied": 0, "positive": 0, "won": 0})
    rows = db.execute(select(Company.segment_key, Company.status, Company.id).where(
        Company.status.in_(["contacted", "replied", "meeting", "won", "lost"]))).all()
    for seg, status, _ in rows:
        k = seg or "unknown"
        stats[k]["sent"] += 1
        if status in ("replied", "meeting", "won"):
            stats[k]["replied"] += 1
        if status in ("meeting", "won"):
            stats[k]["positive"] += 1
        if status == "won":
            stats[k]["won"] += 1
    out = {}
    for k, s in stats.items():
        rr, pr, score = _rates(s["sent"], s["replied"], s["positive"])
        out[k] = {**s, "reply_rate": round(rr, 3), "positive_rate": round(pr, 3), "score": round(score, 4)}
    return out


def suggest_segment_multipliers(db: Session, min_sent: int = 5) -> list[dict[str, Any]]:
    perf = segment_performance(db)
    if not perf:
        return []
    baseline = _rates(0, 0, 0)[2]
    current = get_setting(db, "segment_priorities")
    out = []
    for seg in SEGMENTS:
        p = perf.get(seg.key)
        if not p or p["sent"] < min_sent:
            continue
        ratio = p["score"] / baseline if baseline else 1.0
        suggested = round(max(0.6, min(1.4, 0.5 + 0.5 * ratio)), 2)
        cur = float(current.get(seg.key, {}).get("multiplier", 1.0))
        if abs(suggested - cur) >= 0.05:
            out.append({"segment_key": seg.key, "label": seg.label, "current": cur, "suggested": suggested,
                        "sent": p["sent"], "replied": p["replied"], "positive": p["positive"],
                        "reason": f"Odpovědi {p['replied']}/{p['sent']}, kladné {p['positive']} (vyhlazená míra {p['reply_rate'] * 100:.0f} %)"})
    return out


def apply_suggestions(db: Session, suggestions: list[dict[str, Any]]) -> dict:
    current = get_setting(db, "segment_priorities")
    for s in suggestions:
        cfg = current.setdefault(s["segment_key"], {"enabled": True, "multiplier": 1.0})
        cfg["multiplier"] = s["suggested"]
    return set_setting(db, "segment_priorities", current)
