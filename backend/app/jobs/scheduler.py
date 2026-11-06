"""Plánovač (APScheduler) – zakládá úlohy do fronty podle nastavení."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..db import SessionLocal
from ..settings_store import get_setting
from .queue import enqueue

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _enqueue_scheduled(job_type: str, dedupe: str) -> None:
    with SessionLocal() as db:
        if get_setting(db, "automation").get("paused"):
            log.info("Automatizace pozastavena – %s přeskočeno", job_type)
            return
        enqueue(db, job_type, {}, priority=40, dedupe_key=dedupe, trigger="scheduler")
        db.commit()


def daily_pipeline_tick() -> None:
    from datetime import date

    _enqueue_scheduled("daily_pipeline", f"daily_pipeline:{date.today().isoformat()}")


def followup_tick() -> None:
    _enqueue_scheduled("followup_check", "followup_check")


def sources_tick() -> None:
    _enqueue_scheduled("check_sources", "check_sources")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True)
    reschedule()
    _scheduler.add_job(followup_tick, IntervalTrigger(hours=1), id="followup_check", replace_existing=True)
    _scheduler.add_job(sources_tick, IntervalTrigger(hours=12), id="check_sources", replace_existing=True)
    _scheduler.start()
    log.info("Plánovač spuštěn")
    catch_up_daily()
    return _scheduler


def catch_up_daily() -> bool:
    """Pokud server dnes v čase denního běhu neběžel (uspaný hosting, vypnutý počítač), dožene ho."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import select

    from ..models import AutomationJob

    with SessionLocal() as db:
        cfg = get_setting(db, "automation")
        if cfg.get("paused"):
            return False
        tz = ZoneInfo(cfg.get("timezone", "Europe/Prague"))
        now = datetime.now(tz)
        due = now.replace(hour=int(cfg["daily_run_hour"]), minute=int(cfg["daily_run_minute"]), second=0, microsecond=0)
        if now < due:
            return False
        start_utc = due.replace(hour=0, minute=0).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        ran = db.scalar(select(AutomationJob.id).where(AutomationJob.job_type == "daily_pipeline",
                                                       AutomationJob.created_at >= start_utc).limit(1))
        if ran:
            return False
        enqueue(db, "daily_pipeline", {"catch_up": True}, priority=40,
                dedupe_key=f"daily_pipeline:{now.date().isoformat()}", trigger="scheduler")
        db.commit()
        log.info("Dnešní denní běh byl zmeškán – spouštím ho dodatečně")
        return True


def reschedule() -> None:
    if _scheduler is None:
        return
    with SessionLocal() as db:
        cfg = get_setting(db, "automation")
    trig = CronTrigger(hour=int(cfg["daily_run_hour"]), minute=int(cfg["daily_run_minute"]), timezone=cfg.get("timezone", "Europe/Prague"))
    _scheduler.add_job(daily_pipeline_tick, trig, id="daily_pipeline", replace_existing=True)


def next_runs() -> list[dict]:
    if _scheduler is None:
        return []
    return [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None} for j in _scheduler.get_jobs()]


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
