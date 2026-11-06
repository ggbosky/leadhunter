"""Perzistentní fronta úloh v databázi + worker vlákna.

- úlohy přežijí restart (tabulka automation_jobs),
- atomické převzetí úlohy (optimistický zámek přes UPDATE ... WHERE status='queued'),
- retry s exponenciálním čekáním,
- deduplikace přes dedupe_key,
- pozastavení automatizace (pozastaví úlohy plánovače; ruční úlohy běží dál).
"""
from __future__ import annotations

import logging
import socket
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import AutomationJob, utcnow
from ..settings_store import get_setting

log = logging.getLogger(__name__)

HANDLERS: dict[str, Callable[[Session, AutomationJob], dict[str, Any] | None]] = {}

JOB_LABELS = {
    "discover": "Vyhledání firem",
    "analyze": "Analýza webu",
    "analyze_batch": "Výběr webů k analýze",
    "score_all": "Přepočet skóre",
    "generate_messages": "Příprava zpráv",
    "prepare_messages": "Výběr leadů pro zprávy",
    "daily_pipeline": "Denní automatizace",
    "daily_report": "Denní přehled",
    "followup_check": "Kontrola follow-upů",
    "check_sources": "Kontrola zdrojů dat",
}


class JobDeferred(Exception):
    """Úloha čeká na dokončení jiných úloh – odloží se bez započtení pokusu."""

    def __init__(self, seconds: int = 60, reason: str = "") -> None:
        super().__init__(reason)
        self.seconds = seconds
        self.reason = reason


def handler(job_type: str):
    def deco(fn):
        HANDLERS[job_type] = fn
        return fn
    return deco


def enqueue(db: Session, job_type: str, payload: dict | None = None, *, priority: int = 100, dedupe_key: str | None = None,
            run_after: datetime | None = None, trigger: str = "manual", max_attempts: int = 3,
            parent_id: int | None = None) -> AutomationJob:
    if dedupe_key:
        existing = db.scalar(select(AutomationJob).where(AutomationJob.dedupe_key == dedupe_key,
                                                         AutomationJob.status.in_(["queued", "running"])).limit(1))
        if existing:
            return existing
    job = AutomationJob(job_type=job_type, payload=payload or {}, priority=priority, dedupe_key=dedupe_key,
                        run_after=run_after or utcnow(), trigger=trigger, max_attempts=max_attempts, parent_id=parent_id,
                        status="queued", log=[])
    db.add(job)
    db.flush()
    return job


def job_log(job: AutomationJob, message: str) -> None:
    entries = list(job.log or [])
    entries.append({"t": utcnow().isoformat(timespec="seconds"), "m": message[:500]})
    job.log = entries[-100:]


# krátké úlohy spouštěné z UI (ne dávkové vyhledávání)
INTERACTIVE_TYPES = ["analyze", "generate_messages", "score_all", "check_sources", "daily_report", "followup_check"]


def claim_next(db: Session, worker: str, manual_only: bool = False, job_types: list[str] | None = None) -> AutomationJob | None:
    now = utcnow()
    q = select(AutomationJob.id).where(AutomationJob.status == "queued", AutomationJob.run_after <= now)
    if manual_only:
        q = q.where(AutomationJob.trigger == "manual")
    if job_types:
        q = q.where(AutomationJob.job_type.in_(job_types))
    ids = db.scalars(q.order_by(AutomationJob.priority, AutomationJob.id).limit(5)).all()
    for jid in ids:
        res = db.execute(update(AutomationJob).where(AutomationJob.id == jid, AutomationJob.status == "queued")
                         .values(status="running", started_at=now, worker=worker, attempts=AutomationJob.attempts + 1))
        db.commit()
        if res.rowcount == 1:
            return db.get(AutomationJob, jid)
    return None


def run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AutomationJob, job_id)
        if job is None:
            return
        fn = HANDLERS.get(job.job_type)
        if fn is None:
            job.status = "failed"
            job.last_error = f"Neznámý typ úlohy {job.job_type}"
            job.finished_at = utcnow()
            db.commit()
            return
        try:
            result = fn(db, job)
            db.commit()
            job = db.get(AutomationJob, job_id)
            job.status = "done"
            job.result = result or {}
            job.finished_at = utcnow()
            job.last_error = None
            db.commit()
        except JobDeferred as d:
            db.rollback()
            job = db.get(AutomationJob, job_id)
            job.status = "queued"
            job.attempts = max(0, job.attempts - 1)
            job.run_after = utcnow() + timedelta(seconds=d.seconds)
            job_log(job, f"Odloženo: {d.reason}")
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(AutomationJob, job_id)
            err = f"{type(exc).__name__}: {exc}"
            log.error("Úloha %s #%s selhala: %s", job.job_type, job.id, err)
            job.last_error = (err + "\n" + traceback.format_exc()[-3000:])[:6000]
            job_log(job, f"Chyba (pokus {job.attempts}/{job.max_attempts}): {err}")
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.run_after = utcnow() + timedelta(seconds=min(3600, 60 * 2 ** (job.attempts - 1)))
            else:
                job.status = "failed"
                job.finished_at = utcnow()
            db.commit()
    finally:
        db.close()


def recover_stale(db: Session, older_than_minutes: int = 30) -> int:
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    res = db.execute(update(AutomationJob).where(AutomationJob.status == "running", AutomationJob.started_at < cutoff)
                     .values(status="queued", run_after=utcnow()))
    db.commit()
    return res.rowcount or 0


def children_pending(db: Session, parent_id: int, job_types: list[str] | None = None) -> int:
    q = select(AutomationJob.id).where(AutomationJob.parent_id == parent_id, AutomationJob.status.in_(["queued", "running"]))
    if job_types:
        q = q.where(AutomationJob.job_type.in_(job_types))
    return len(db.scalars(q).all())


class Worker:
    def __init__(self, concurrency: int | None = None) -> None:
        s = get_settings()
        self.concurrency = concurrency or s.worker_concurrency
        self.poll = s.worker_poll_seconds
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.name = f"{socket.gethostname()}"
        self.current: dict[str, int | None] = {}

    def start(self) -> None:
        with SessionLocal() as db:
            n = recover_stale(db, older_than_minutes=0)
            if n:
                log.info("Obnoveno %s nedokončených úloh po restartu", n)
        for i in range(self.concurrency):
            t = threading.Thread(target=self._loop, args=(f"{self.name}-{i}",), daemon=True, name=f"lh-worker-{i}")
            t.start()
            self._threads.append(t)
        # vyhrazené vlákno pro ruční akce z UI – nečekají za dlouhou automatizací
        t = threading.Thread(target=self._loop, args=(f"{self.name}-interactive", True), daemon=True, name="lh-worker-ui")
        t.start()
        self._threads.append(t)
        log.info("Worker spuštěn (%s vláken + 1 pro ruční akce)", self.concurrency)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=timeout)

    def _loop(self, wname: str, interactive: bool = False) -> None:
        while not self._stop.is_set():
            try:
                with SessionLocal() as db:
                    paused = bool(get_setting(db, "automation").get("paused"))
                    job = claim_next(db, wname, manual_only=paused or interactive,
                                     job_types=INTERACTIVE_TYPES if interactive else None)
                if job is None:
                    self._stop.wait(self.poll)
                    continue
                self.current[wname] = job.id
                log.info("[%s] Spouštím %s #%s", wname, job.job_type, job.id)
                run_job(job.id)
            except Exception:  # noqa: BLE001
                log.exception("Chyba ve smyčce workeru")
                time.sleep(self.poll)
            finally:
                self.current[wname] = None


def run_pending_sync(max_jobs: int = 100) -> int:
    """Spustí čekající úlohy synchronně (CLI / testy)."""
    n = 0
    while n < max_jobs:
        with SessionLocal() as db:
            job = claim_next(db, "sync")
        if job is None:
            break
        run_job(job.id)
        n += 1
    return n
