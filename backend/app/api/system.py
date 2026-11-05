"""API: dashboard, discovery, zdroje, automatizace, úlohy, nastavení, učení, DNC, kampaně, úkoly."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import DiscoveryQuery
from ..connectors.registry import check_all, connectors, ensure_data_sources
from ..db import get_db
from ..jobs import scheduler
from ..jobs.queue import JOB_LABELS, enqueue
from ..models import AutomationJob, Campaign, Company, DataSource, FollowUpTask, SuppressionEntry, utcnow
from ..regions import REGIONS
from ..scoring.engine import CATEGORY_LABELS, DISQUALIFICATION_LABELS
from ..segments import SEGMENTS, SERVICES, TIER_LABELS, get_segment
from ..services.discovery import run_discovery
from ..services.learning import apply_suggestions, segment_performance, strategy_performance, suggest_segment_multipliers
from ..services.llm import get_provider, hardware_info
from ..services.messages import MESSAGE_TYPES, STRATEGIES
from ..services.normalize import normalize_domain, normalize_ico, normalize_linkedin
from ..services.outreach import complete_task
from ..services.reports import build_daily_report, dashboard_stats
from ..services.screenshots import playwright_available
from ..services.signals import SIGNAL_LABELS
from ..services.suppression import SUPPRESSION_REASONS, suppress_company
from ..settings_store import DEFAULTS, all_settings, get_setting, set_setting
from .serializers import job_dict, suppression_dict, task_dict

router = APIRouter()

COMPANY_STATUSES = {
    "new": "Nová", "analyzed": "Analyzovaná", "qualified": "Kvalifikovaná", "contacted": "Oslovená", "replied": "Odpověděla",
    "meeting": "Schůzka", "won": "Získaná", "lost": "Ztracená", "disqualified": "Vyřazená",
}


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "time": utcnow().isoformat() + "Z"}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "segments": [{"key": s.key, "label": s.label, "tier": s.tier, "economic_base": s.economic_base,
                      "visual_importance": s.visual_importance, "typical_service": s.typical_service} for s in SEGMENTS],
        "tiers": TIER_LABELS,
        "regions": [{"code": r.code, "name": r.name, "country": r.country, "cities": r.cities, "default_priority": r.default_priority} for r in REGIONS],
        "strategies": STRATEGIES,
        "message_types": MESSAGE_TYPES,
        "statuses": COMPANY_STATUSES,
        "categories": CATEGORY_LABELS,
        "disqualification_reasons": DISQUALIFICATION_LABELS,
        "services": SERVICES,
        "signal_types": SIGNAL_LABELS,
        "suppression_reasons": SUPPRESSION_REASONS,
        "job_types": JOB_LABELS,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    stats = dashboard_stats(db)
    last_report = db.scalar(select(AutomationJob).where(AutomationJob.job_type == "daily_report", AutomationJob.status == "done")
                            .order_by(AutomationJob.id.desc()).limit(1))
    return {**stats, "last_report": last_report.result if last_report else None,
            "last_report_at": last_report.finished_at.isoformat() + "Z" if last_report and last_report.finished_at else None,
            "automation_paused": bool(get_setting(db, "automation").get("paused"))}


@router.get("/reports/daily")
def daily_report(fresh: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not fresh:
        j = db.scalar(select(AutomationJob).where(AutomationJob.job_type == "daily_report", AutomationJob.status == "done")
                      .order_by(AutomationJob.id.desc()).limit(1))
        if j and j.result:
            return j.result
    return build_daily_report(db)


# ---------------------------------------------------------------------------
# Discovery a zdroje
# ---------------------------------------------------------------------------
class DiscoveryBody(BaseModel):
    segment_key: str | None = None
    region_code: str | None = None
    city: str | None = None
    country: str = "CZ"
    keyword: str | None = None
    sources: list[str] | None = None
    limit: int = Field(40, ge=1, le=300)
    require_website: bool = True
    auto_analyze: bool = False
    auto_analyze_limit: int = Field(10, ge=0, le=100)
    sync: bool = False


@router.post("/discovery/run")
def discovery_run(body: DiscoveryBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.segment_key and not get_segment(body.segment_key):
        raise HTTPException(400, "Neznámý segment")
    if not (body.segment_key or body.keyword):
        raise HTTPException(400, "Zadejte obor nebo klíčové slovo")
    if body.sync:
        q = DiscoveryQuery(segment_key=body.segment_key, region_code=body.region_code, city=body.city, country=body.country,
                           limit=body.limit, require_website=body.require_website, keyword=body.keyword)
        stats = run_discovery(db, q, source_keys=body.sources)
        return stats.to_dict()
    job = enqueue(db, "discover", body.model_dump(exclude={"sync"}), priority=30,
                  dedupe_key=f"discover-manual:{body.segment_key}:{body.region_code}:{body.city}:{body.keyword}")
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.get("/sources")
def sources(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    ds = ensure_data_sources(db)
    db.commit()
    out = []
    for key, c in connectors().items():
        d = ds[key]
        out.append({**c.describe(), "enabled": d.enabled, "last_status": d.last_status, "last_error": d.last_error,
                    "last_check_at": d.last_check_at.isoformat() + "Z" if d.last_check_at else None,
                    "total_requests": d.total_requests, "total_errors": d.total_errors, "total_records": d.total_records})
    return out


@router.post("/sources/check")
def sources_check(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    res = check_all(db)
    db.commit()
    return res


class SourcePatch(BaseModel):
    enabled: bool


@router.patch("/sources/{key}")
def source_patch(key: str, body: SourcePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_data_sources(db)
    d = db.scalar(select(DataSource).where(DataSource.key == key))
    if not d:
        raise HTTPException(404, "Zdroj nenalezen")
    d.enabled = body.enabled
    db.commit()
    return {"key": key, "enabled": d.enabled}


# ---------------------------------------------------------------------------
# Automatizace a úlohy
# ---------------------------------------------------------------------------
@router.get("/automation")
def automation_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..main import WORKER

    cfg = get_setting(db, "automation")
    since = utcnow() - timedelta(hours=24)
    recent = db.scalars(select(AutomationJob).where(AutomationJob.created_at >= since)).all()
    counts: dict[str, int] = {}
    for j in recent:
        counts[j.status] = counts.get(j.status, 0) + 1
    return {
        "config": cfg,
        "paused": bool(cfg.get("paused")),
        "scheduler_running": scheduler._scheduler is not None,
        "next_runs": scheduler.next_runs(),
        "worker_running": WORKER is not None,
        "worker_threads": WORKER.concurrency if WORKER else 0,
        "worker_current": WORKER.current if WORKER else {},
        "last_24h": counts,
    }


@router.post("/automation/pause")
def pause(db: Session = Depends(get_db)) -> dict[str, Any]:
    cfg = get_setting(db, "automation")
    cfg["paused"] = True
    set_setting(db, "automation", cfg)
    db.commit()
    return {"paused": True}


@router.post("/automation/resume")
def resume(db: Session = Depends(get_db)) -> dict[str, Any]:
    cfg = get_setting(db, "automation")
    cfg["paused"] = False
    set_setting(db, "automation", cfg)
    db.commit()
    return {"paused": False}


@router.post("/automation/run-daily")
def run_daily(db: Session = Depends(get_db)) -> dict[str, Any]:
    job = enqueue(db, "daily_pipeline", {}, priority=40, trigger="manual", dedupe_key="daily_pipeline:manual")
    db.commit()
    return {"job_id": job.id}


class JobCreate(BaseModel):
    job_type: Literal["analyze_batch", "score_all", "prepare_messages", "daily_report", "followup_check", "check_sources"]
    payload: dict[str, Any] = {}


@router.post("/jobs")
def create_job(body: JobCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = enqueue(db, body.job_type, body.payload, priority=30, trigger="manual", dedupe_key=f"{body.job_type}:manual")
    db.commit()
    return job_dict(job)


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), status: str | None = None, job_type: str | None = None,
              limit: int = Query(100, le=500)) -> list[dict[str, Any]]:
    q = select(AutomationJob)
    if status:
        q = q.where(AutomationJob.status.in_(status.split(",")))
    if job_type:
        q = q.where(AutomationJob.job_type == job_type)
    return [job_dict(j) for j in db.scalars(q.order_by(AutomationJob.id.desc()).limit(limit))]


@router.post("/jobs/{jid}/retry")
def retry_job(jid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = db.get(AutomationJob, jid)
    if not j:
        raise HTTPException(404, "Úloha nenalezena")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Opakovat lze jen selhanou nebo zrušenou úlohu")
    j.status, j.attempts, j.run_after, j.last_error = "queued", 0, utcnow(), None
    j.trigger = "manual"
    db.commit()
    return job_dict(j)


@router.post("/jobs/{jid}/cancel")
def cancel_job(jid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = db.get(AutomationJob, jid)
    if not j:
        raise HTTPException(404, "Úloha nenalezena")
    if j.status != "queued":
        raise HTTPException(409, "Zrušit lze jen čekající úlohu")
    j.status = "cancelled"
    j.finished_at = utcnow()
    db.commit()
    return job_dict(j)


# ---------------------------------------------------------------------------
# Nastavení, AI, učení
# ---------------------------------------------------------------------------
@router.get("/settings")
def get_settings_all(db: Session = Depends(get_db)) -> dict[str, Any]:
    return all_settings(db)


@router.put("/settings/{key}")
def put_setting(key: str, value: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if key not in DEFAULTS:
        raise HTTPException(404, "Neznámé nastavení")
    if key == "scoring":
        w = (value.get("weights") or {})
        if w and abs(sum(float(x) for x in w.values()) - 1.0) > 0.02:
            raise HTTPException(400, "Součet vah musí být 1,0 (100 %)")
    res = set_setting(db, key, value)
    db.commit()
    if key == "automation":
        scheduler.reschedule()
    if key in ("scoring", "segment_priorities", "pricing"):
        enqueue(db, "score_all", {}, priority=35, dedupe_key="score_all", trigger="manual")
        db.commit()
    return res


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    text, tnote = get_provider("text", use_cache=False)
    vision, vnote = get_provider("vision", use_cache=False)
    pw_ok, pw_note = playwright_available()
    return {
        "text": {"available": text is not None, "provider": text.name if text else None, "model": text.model if text else None, "note": tnote},
        "vision": {"available": vision is not None, "provider": vision.name if vision else None, "model": vision.model if vision else None, "note": vnote},
        "playwright": {"available": pw_ok, "note": pw_note},
        "hardware": hardware_info(),
    }


@router.get("/learning")
def learning(db: Session = Depends(get_db)) -> dict[str, Any]:
    seg = segment_performance(db)
    return {
        "strategies": strategy_performance(db),
        "segments": [{"segment_key": k, "label": (get_segment(k).label if get_segment(k) else "Neurčeno"), **v} for k, v in seg.items()],
        "suggestions": suggest_segment_multipliers(db),
    }


@router.post("/learning/apply")
def learning_apply(db: Session = Depends(get_db)) -> dict[str, Any]:
    sug = suggest_segment_multipliers(db)
    res = apply_suggestions(db, sug)
    enqueue(db, "score_all", {}, priority=35, dedupe_key="score_all", trigger="manual")
    db.commit()
    return {"applied": len(sug), "segment_priorities": res}


# ---------------------------------------------------------------------------
# Do Not Contact
# ---------------------------------------------------------------------------
@router.get("/suppression")
def list_suppression(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [suppression_dict(s) for s in db.scalars(select(SuppressionEntry).order_by(SuppressionEntry.id.desc()))]


class SuppressionBody(BaseModel):
    company_id: int | None = None
    domain: str | None = None
    ico: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    name: str | None = None
    reason: str = "manual"
    note: str | None = None


@router.post("/suppression")
def add_suppression(body: SuppressionBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.company_id:
        c = db.get(Company, body.company_id)
        if not c:
            raise HTTPException(404, "Firma nenalezena")
        e = suppress_company(db, c, body.reason, note=body.note)
        db.commit()
        return suppression_dict(e)
    if not any([body.domain, body.ico, body.email, body.linkedin_url]):
        raise HTTPException(400, "Zadejte doménu, IČO, e-mail nebo LinkedIn URL")
    e = SuppressionEntry(domain=normalize_domain(body.domain) if body.domain else None, ico=normalize_ico(body.ico),
                         email=(body.email or "").lower() or None, linkedin_url=normalize_linkedin(body.linkedin_url),
                         name=body.name, reason=body.reason, note=body.note)
    db.add(e)
    db.flush()
    # okamžitě aplikuj na existující firmy
    conds = []
    if e.domain:
        conds.append(Company.domain == e.domain)
    if e.ico:
        conds.append(Company.ico == e.ico)
    if e.email:
        conds.append(Company.email == e.email)
    if conds:
        from sqlalchemy import or_

        for c in db.scalars(select(Company).where(or_(*conds))):
            suppress_company(db, c, body.reason, note=body.note)
    db.commit()
    return suppression_dict(e)


@router.delete("/suppression/{sid}")
def delete_suppression(sid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(SuppressionEntry, sid)
    if not e:
        raise HTTPException(404, "Záznam nenalezen")
    db.delete(e)
    db.commit()
    return {"deleted": sid}


# ---------------------------------------------------------------------------
# Kampaně
# ---------------------------------------------------------------------------
class CampaignBody(BaseModel):
    name: str
    description: str | None = None
    segment_keys: list[str] = []
    region_codes: list[str] = []
    default_strategy: str | None = None
    active: bool = True


def campaign_dict(db: Session, c: Campaign) -> dict[str, Any]:
    from sqlalchemy import func

    n = db.scalar(select(func.count(Company.id)).where(Company.campaign_id == c.id)) or 0
    contacted = db.scalar(select(func.count(Company.id)).where(Company.campaign_id == c.id,
                                                               Company.status.in_(["contacted", "replied", "meeting", "won", "lost"]))) or 0
    replied = db.scalar(select(func.count(Company.id)).where(Company.campaign_id == c.id, Company.status.in_(["replied", "meeting", "won"]))) or 0
    return {"id": c.id, "name": c.name, "description": c.description, "segment_keys": c.segment_keys, "region_codes": c.region_codes,
            "default_strategy": c.default_strategy, "active": c.active, "companies": n, "contacted": contacted, "replied": replied,
            "created_at": c.created_at.isoformat() + "Z"}


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [campaign_dict(db, c) for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()))]


@router.post("/campaigns")
def create_campaign(body: CampaignBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.scalar(select(Campaign).where(Campaign.name == body.name)):
        raise HTTPException(409, "Kampaň s tímto názvem existuje")
    c = Campaign(**body.model_dump())
    db.add(c)
    db.flush()
    # přiřaď odpovídající neoslovené firmy
    q = select(Company).where(Company.campaign_id.is_(None), Company.status.in_(["new", "analyzed", "qualified"]))
    if body.segment_keys:
        q = q.where(Company.segment_key.in_(body.segment_keys))
    if body.region_codes:
        q = q.where(Company.region_code.in_(body.region_codes))
    for comp in db.scalars(q):
        comp.campaign_id = c.id
    db.commit()
    return campaign_dict(db, c)


@router.patch("/campaigns/{cid}")
def patch_campaign(cid: int, body: CampaignBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404, "Kampaň nenalezena")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return campaign_dict(db, c)


# ---------------------------------------------------------------------------
# Follow-up úkoly
# ---------------------------------------------------------------------------
@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db), scope: Literal["due", "upcoming", "open", "done", "all"] = "open") -> list[dict[str, Any]]:
    q = select(FollowUpTask)
    now = utcnow()
    if scope == "due":
        q = q.where(FollowUpTask.status == "open", FollowUpTask.due_at <= now + timedelta(hours=24))
    elif scope == "upcoming":
        q = q.where(FollowUpTask.status == "open", FollowUpTask.due_at > now)
    elif scope == "open":
        q = q.where(FollowUpTask.status == "open")
    elif scope == "done":
        q = q.where(FollowUpTask.status.in_(["done", "cancelled"]))
    return [task_dict(t, with_company=True) for t in db.scalars(q.order_by(FollowUpTask.due_at).limit(500))]


class TaskComplete(BaseModel):
    sent: bool = False


@router.post("/tasks/{tid}/complete")
def task_complete(tid: int, body: TaskComplete, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(FollowUpTask, tid)
    if not t:
        raise HTTPException(404, "Úkol nenalezen")
    nxt = complete_task(db, t, sent=body.sent)
    db.commit()
    return {"task": task_dict(t), "next_task": task_dict(nxt) if nxt else None}


class TaskPatch(BaseModel):
    due_at: str | None = None
    title: str | None = None
    status: Literal["open", "cancelled"] | None = None


@router.patch("/tasks/{tid}")
def task_patch(tid: int, body: TaskPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    from datetime import datetime

    t = db.get(FollowUpTask, tid)
    if not t:
        raise HTTPException(404, "Úkol nenalezen")
    if body.due_at:
        t.due_at = datetime.fromisoformat(body.due_at.replace("Z", "")).replace(tzinfo=None)
    if body.title:
        t.title = body.title
    if body.status:
        t.status = body.status
        if body.status == "cancelled":
            t.cancelled_reason = "Zrušeno ručně"
            t.completed_at = utcnow()
    db.commit()
    return task_dict(t, with_company=True)
