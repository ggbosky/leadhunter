"""Denní přehled a statistiky pro dashboard."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AutomationJob, Company, DataSource, FollowUpTask, LeadScore, OutreachEvent, OutreachMessage, utcnow
from ..segments import get_segment


def _start_of_day():
    n = utcnow()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def build_daily_report(db: Session) -> dict[str, Any]:
    since = _start_of_day()
    new_companies = db.scalar(select(func.count(Company.id)).where(Company.first_seen_at >= since)) or 0
    analyzed = db.scalar(select(func.count(Company.id)).where(Company.last_analyzed_at >= since)) or 0
    msgs = db.scalar(select(func.count(func.distinct(OutreachMessage.company_id))).where(OutreachMessage.created_at >= since)) or 0
    due = db.scalar(select(func.count(FollowUpTask.id)).where(FollowUpTask.status == "open", FollowUpTask.due_at <= utcnow() + timedelta(hours=24))) or 0
    failed = db.scalars(select(AutomationJob).where(AutomationJob.status == "failed", AutomationJob.finished_at >= since)).all()
    top = db.execute(
        select(Company, LeadScore).join(LeadScore, (LeadScore.company_id == Company.id) & LeadScore.is_current.is_(True))
        .where(Company.status.in_(["qualified", "analyzed"]), LeadScore.opportunity_score.is_not(None))
        .order_by(LeadScore.opportunity_score.desc()).limit(10)
    ).all()
    sources = db.scalars(select(DataSource)).all()
    return {
        "date": since.date().isoformat(),
        "new_companies": new_companies,
        "analyzed": analyzed,
        "messages_prepared_for": msgs,
        "followups_due_24h": due,
        "failed_jobs": [{"id": j.id, "type": j.job_type, "error": (j.last_error or "")[:200]} for j in failed[:20]],
        "top_leads": [{"company_id": c.id, "name": c.name, "segment": (get_segment(c.segment_key).label if get_segment(c.segment_key) else None),
                       "score": s.opportunity_score, "category": s.category, "reason": s.outreach_reason} for c, s in top],
        "sources": [{"key": s.key, "name": s.name, "status": s.last_status, "error": s.last_error} for s in sources],
    }


def dashboard_stats(db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count(Company.id))) or 0
    by_status = dict(db.execute(select(Company.status, func.count(Company.id)).group_by(Company.status)).all())
    cat_rows = db.execute(select(LeadScore.category, func.count(LeadScore.id)).where(LeadScore.is_current.is_(True)).group_by(LeadScore.category)).all()
    by_segment_rows = db.execute(
        select(Company.segment_key, func.count(Company.id), func.avg(LeadScore.opportunity_score))
        .outerjoin(LeadScore, (LeadScore.company_id == Company.id) & LeadScore.is_current.is_(True))
        .group_by(Company.segment_key)).all()
    by_region = db.execute(select(Company.region_code, func.count(Company.id)).group_by(Company.region_code)).all()
    # funnel
    contacted = db.scalar(select(func.count(func.distinct(OutreachEvent.company_id))).where(
        OutreachEvent.event_type.in_(["message_sent", "connection_requested"]))) or 0
    replied = db.scalar(select(func.count(func.distinct(OutreachEvent.company_id))).where(OutreachEvent.event_type.in_(["replied", "meeting", "won", "not_interested"]))) or 0
    meetings = db.scalar(select(func.count(func.distinct(OutreachEvent.company_id))).where(OutreachEvent.event_type.in_(["meeting", "won"]))) or 0
    won = db.scalar(select(func.count(func.distinct(OutreachEvent.company_id))).where(OutreachEvent.event_type == "won")) or 0
    # aktivita 14 dní
    since = _start_of_day() - timedelta(days=13)
    disc = dict(db.execute(select(func.date(Company.first_seen_at), func.count(Company.id)).where(Company.first_seen_at >= since)
                           .group_by(func.date(Company.first_seen_at))).all())
    ana = dict(db.execute(select(func.date(Company.last_analyzed_at), func.count(Company.id)).where(Company.last_analyzed_at >= since)
                          .group_by(func.date(Company.last_analyzed_at))).all())
    sent = dict(db.execute(select(func.date(OutreachEvent.occurred_at), func.count(OutreachEvent.id)).where(
        OutreachEvent.occurred_at >= since, OutreachEvent.event_type.in_(["message_sent", "connection_requested", "follow_up_sent"]))
        .group_by(func.date(OutreachEvent.occurred_at))).all())
    # Postgres vrací date, SQLite řetězec – sjednotit klíče
    disc = {str(k): v for k, v in disc.items()}
    ana = {str(k): v for k, v in ana.items()}
    sent = {str(k): v for k, v in sent.items()}
    days = []
    for i in range(14):
        d = (since + timedelta(days=i)).date().isoformat()
        days.append({"date": d, "discovered": disc.get(d, 0), "analyzed": ana.get(d, 0), "contacted": sent.get(d, 0)})
    hist_rows = db.scalars(select(LeadScore.opportunity_score).where(LeadScore.is_current.is_(True), LeadScore.opportunity_score.is_not(None))).all()
    hist = [{"bucket": f"{b}–{b + 9}", "count": sum(1 for v in hist_rows if b <= v < b + 10 or (b == 90 and v == 100))} for b in range(0, 100, 10)]
    due_today = db.scalar(select(func.count(FollowUpTask.id)).where(FollowUpTask.status == "open", FollowUpTask.due_at <= utcnow())) or 0
    queue = dict(db.execute(select(AutomationJob.status, func.count(AutomationJob.id)).group_by(AutomationJob.status)).all())
    return {
        "total_companies": total,
        "by_status": by_status,
        "by_category": {k or "none": v for k, v in cat_rows},
        "by_segment": [{"segment_key": k, "label": (get_segment(k).label if get_segment(k) else "Neurčeno"), "count": n,
                        "avg_score": round(a, 1) if a is not None else None} for k, n, a in by_segment_rows],
        "by_region": [{"region_code": k, "count": n} for k, n in by_region],
        "funnel": {"qualified": by_status.get("qualified", 0), "contacted": contacted, "replied": replied, "meetings": meetings, "won": won},
        "activity": days,
        "score_histogram": hist,
        "followups_due": due_today,
        "queue": queue,
    }
