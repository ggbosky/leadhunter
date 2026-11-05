"""Obsluha jednotlivých typů úloh automatizace."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..connectors.base import DiscoveryQuery
from ..connectors.registry import check_all
from ..models import AutomationJob, Company, LeadScore, OutreachMessage, utcnow
from ..regions import REGION_BY_CODE
from ..segments import get_segment
from ..settings_store import get_setting
from ..services.discovery import plan_discovery_queries, run_discovery
from ..services.messages import generate_message_set
from ..services.pipeline import analyze_company, score_company
from ..services.reports import build_daily_report
from .queue import JobDeferred, children_pending, enqueue, handler, job_log

log = logging.getLogger(__name__)


def _today_start():
    n = utcnow()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


@handler("discover")
def h_discover(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    q = DiscoveryQuery(segment_key=p.get("segment_key"), region_code=p.get("region_code"), city=p.get("city"),
                       country=p.get("country") or "CZ", limit=int(p.get("limit") or 40),
                       require_website=bool(p.get("require_website", True)), keyword=p.get("keyword"))
    stats = run_discovery(db, q, source_keys=p.get("sources"), max_new=p.get("max_new"))
    job_log(job, f"Nalezeno {stats.found}, nových {stats.created}, aktualizováno {stats.updated}")
    if stats.errors:
        job_log(job, "Chyby zdrojů: " + "; ".join(stats.errors)[:400])
    if p.get("auto_analyze") and stats.company_ids:
        for cid in stats.company_ids[: int(p.get("auto_analyze_limit") or 10)]:
            c = db.get(Company, cid)
            if c and c.website_url:
                enqueue(db, "analyze", {"company_id": cid}, priority=70, dedupe_key=f"analyze:{cid}",
                        trigger=job.trigger, parent_id=job.id)
    if stats.sources_used and stats.found == 0 and stats.errors and len(stats.errors) >= len(stats.sources_used):
        raise RuntimeError("Všechny zdroje selhaly: " + "; ".join(stats.errors)[:500])
    return stats.to_dict()


@handler("analyze")
def h_analyze(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    return analyze_company(db, int(p["company_id"]), screenshots=p.get("screenshots", True), vision=p.get("vision", True))


@handler("score_all")
def h_score_all(db: Session, job: AutomationJob) -> dict[str, Any]:
    ids = db.scalars(select(Company.id).where(Company.last_analyzed_at.is_not(None))).all()
    for cid in ids:
        c = db.get(Company, cid)
        if c:
            score_company(db, c)
    db.commit()
    return {"rescored": len(ids)}


@handler("generate_messages")
def h_generate(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    c = db.get(Company, int(p["company_id"]))
    if c is None:
        raise ValueError("Firma neexistuje")
    msgs = generate_message_set(db, c, strategy=p.get("strategy"))
    db.commit()
    return {"messages": len(msgs), "strategy": msgs[0].strategy if msgs else None, "generator": msgs[0].generator if msgs else None}


def _analysis_candidates(db: Session, limit: int) -> list[int]:
    seg_prio = get_setting(db, "segment_priorities")
    reg_prio = get_setting(db, "region_priorities")
    reanalyze = int(get_setting(db, "automation").get("reanalyze_after_days", 60))
    cutoff = utcnow() - timedelta(days=reanalyze)
    rows = db.scalars(select(Company).where(
        Company.website_url.is_not(None),
        Company.status.in_(["new", "analyzed", "qualified"]),
        or_(Company.last_analyzed_at.is_(None), Company.last_analyzed_at < cutoff),
    ).limit(2000)).all()

    def prio(c: Company) -> float:
        seg = get_segment(c.segment_key)
        tier_w = {1: 3.0, 2: 2.0, 3: 1.0}.get(seg.tier if seg else 3, 0.8)
        cfg = seg_prio.get(c.segment_key or "", {"enabled": True, "multiplier": 1.0})
        if not cfg.get("enabled", True):
            return -1
        rp = reg_prio.get(c.region_code or "", {}).get("priority", 2)
        never = 1.5 if c.last_analyzed_at is None else 1.0
        return tier_w * float(cfg.get("multiplier", 1.0)) * (1 + rp / 5) * never

    ranked = sorted((c for c in rows if prio(c) > 0), key=prio, reverse=True)
    out = [c.id for c in ranked[:limit]]
    # firmy bez webu: pokus o dohledání a ověření webu (max. třetina denní kapacity)
    lookup_slots = max(0, min(limit - len(out), max(1, limit // 3)))
    if lookup_slots:
        no_web = db.scalars(select(Company).where(
            Company.website_url.is_(None), Company.website_lookup_at.is_(None), Company.country.in_(["CZ", "SK"]),
            Company.status.in_(["new", "analyzed"]),
        ).limit(500)).all()
        out += [c.id for c in sorted((c for c in no_web if prio(c) > 0), key=prio, reverse=True)[:lookup_slots]]
    return out


@handler("analyze_batch")
def h_analyze_batch(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    if p.get("wait_for_parent") and job.parent_id and children_pending(db, job.parent_id, ["discover"]):
        raise JobDeferred(60, "čekám na dokončení vyhledávání")
    target = int(p.get("limit") or get_setting(db, "automation")["daily_analysis_target"])
    done_today = db.scalar(select(func.count(AutomationJob.id)).where(
        AutomationJob.job_type == "analyze", AutomationJob.status == "done", AutomationJob.finished_at >= _today_start())) or 0
    remaining = max(0, target - done_today) if p.get("respect_daily") else target
    ids = _analysis_candidates(db, remaining)
    for cid in ids:
        enqueue(db, "analyze", {"company_id": cid}, priority=70, dedupe_key=f"analyze:{cid}", trigger=job.trigger,
                parent_id=job.parent_id or job.id)
    job_log(job, f"Naplánováno {len(ids)} analýz (dnes již hotovo {done_today}, cíl {target})")
    return {"enqueued": len(ids), "done_today": done_today, "target": target}


@handler("prepare_messages")
def h_prepare_messages(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    if p.get("wait_for_parent") and job.parent_id and children_pending(db, job.parent_id, ["discover", "analyze_batch", "analyze"]):
        raise JobDeferred(120, "čekám na dokončení analýz")
    cfg = get_setting(db, "automation")
    limit = int(p.get("limit") or cfg["daily_message_target"])
    min_score = float(cfg["min_score_for_messages"])
    has_draft = select(OutreachMessage.company_id).where(OutreachMessage.status.in_(["draft", "sent"]))
    rows = db.execute(
        select(Company, LeadScore).join(LeadScore, (LeadScore.company_id == Company.id) & (LeadScore.is_current.is_(True)))
        .where(Company.status == "qualified", LeadScore.opportunity_score >= min_score, Company.id.not_in(has_draft))
        .order_by(LeadScore.opportunity_score.desc()).limit(limit)
    ).all()
    made = []
    for company, _score in rows:
        try:
            msgs = generate_message_set(db, company)
            db.commit()
            made.append({"company_id": company.id, "strategy": msgs[0].strategy, "generator": msgs[0].generator})
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job_log(job, f"{company.name}: {exc}")
    return {"prepared": len(made), "items": made}


@handler("daily_report")
def h_daily_report(db: Session, job: AutomationJob) -> dict[str, Any]:
    p = job.payload or {}
    if p.get("wait_for_parent") and job.parent_id and children_pending(
            db, job.parent_id, ["discover", "analyze_batch", "analyze", "prepare_messages"]):
        raise JobDeferred(180, "čekám na dokončení denní pipeline")
    return build_daily_report(db)


@handler("followup_check")
def h_followup(db: Session, job: AutomationJob) -> dict[str, Any]:
    from ..services.outreach import due_tasks

    tasks = due_tasks(db)
    return {"due": len(tasks), "items": [{"id": t.id, "title": t.title, "due_at": t.due_at.isoformat()} for t in tasks[:50]]}


@handler("check_sources")
def h_check_sources(db: Session, job: AutomationJob) -> dict[str, Any]:
    res = check_all(db)
    db.commit()
    return {"sources": [{"key": r["key"], "status": r["status"], "detail": r["detail"]} for r in res]}


@handler("daily_pipeline")
def h_daily_pipeline(db: Session, job: AutomationJob) -> dict[str, Any]:
    cfg = get_setting(db, "automation")
    target = int(cfg["daily_discovery_target"])
    queries = plan_discovery_queries(db, limit_queries=max(1, min(25, target // 15 + 1)))
    per_query = max(10, target // max(1, len(queries)))
    for q in queries:
        enqueue(db, "discover", {"segment_key": q.segment_key, "region_code": q.region_code, "country": q.country,
                                 "limit": per_query * 2, "max_new": per_query, "require_website": True},
                priority=50, dedupe_key=f"discover:{q.segment_key}:{q.region_code}", trigger=job.trigger, parent_id=job.id)
    enqueue(db, "analyze_batch", {"wait_for_parent": True, "respect_daily": True}, priority=60, trigger=job.trigger, parent_id=job.id)
    enqueue(db, "prepare_messages", {"wait_for_parent": True}, priority=80, trigger=job.trigger, parent_id=job.id)
    enqueue(db, "followup_check", {}, priority=90, trigger=job.trigger, parent_id=job.id)
    enqueue(db, "daily_report", {"wait_for_parent": True}, priority=95, trigger=job.trigger, parent_id=job.id)
    plan = [f"{get_segment(q.segment_key).label} · {REGION_BY_CODE[q.region_code].name}" for q in queries]
    job_log(job, f"Naplánováno {len(queries)} vyhledávání: " + "; ".join(plan)[:400])
    return {"discovery_queries": plan, "discovery_target": target, "note": "Cíle jsou maxima, ne garantované objemy."}
