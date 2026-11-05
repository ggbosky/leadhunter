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
    return _scheduler


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
