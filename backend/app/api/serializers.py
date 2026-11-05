"""Převod ORM objektů na JSON pro API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..jobs.queue import JOB_LABELS
from ..models import (
    AutomationJob,
    Company,
    Contact,
    FollowUpTask,
    LeadScore,
    OutreachEvent,
    OutreachMessage,
    SuppressionEntry,
)
from ..regions import REGION_BY_CODE
from ..scoring.engine import CATEGORY_LABELS
from ..segments import get_segment
from ..services.linkedin import best_contact, linkedin_links, search_queries
from ..services.messages import MESSAGE_TYPES, STRATEGIES
from ..services.pipeline import current_score, latest_audit, latest_visual, latest_website


def iso(d: datetime | None) -> str | None:
    return d.isoformat() + "Z" if d else None


def screenshot_url(rel: str | None) -> str | None:
    return f"/screenshots/{rel}" if rel else None


def score_dict(s: LeadScore | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "id": s.id, "opportunity_score": s.opportunity_score, "confidence_score": s.confidence_score,
        "category": s.category, "category_label": CATEGORY_LABELS.get(s.category or "", s.category),
        "design_gap": s.design_gap, "commercial_potential": s.commercial_potential, "buying_readiness": s.buying_readiness,
        "service_fit": s.service_fit, "contactability": s.contactability, "business_quality": s.business_quality,
        "website_quality": s.website_quality, "website_quality_basis": s.website_quality_basis,
        "components": s.components, "recommended_service": s.recommended_service, "estimated_budget": s.estimated_budget,
        "outreach_reason": s.outreach_reason, "disqualification_reasons": s.disqualification_reasons,
        "algorithm_version": s.algorithm_version, "computed_at": iso(s.created_at),
    }


def contact_dict(c: Contact) -> dict[str, Any]:
    return {
        "id": c.id, "company_id": c.company_id, "name": c.name, "role": c.role, "email": c.email, "phone": c.phone,
        "linkedin_url": c.linkedin_url, "is_decision_maker": c.is_decision_maker, "is_primary": c.is_primary,
        "verified": c.verified, "source": c.source, "source_evidence": c.source_evidence,
        "connection_status": c.connection_status, "first_contacted_at": iso(c.first_contacted_at),
        "last_contacted_at": iso(c.last_contacted_at), "replied_at": iso(c.replied_at),
        "contact_attempts": c.contact_attempts, "next_step": c.next_step, "next_step_at": iso(c.next_step_at),
        "do_not_contact": c.do_not_contact, "notes": c.notes, "created_at": iso(c.created_at),
    }


def message_dict(m: OutreachMessage) -> dict[str, Any]:
    return {
        "id": m.id, "company_id": m.company_id, "contact_id": m.contact_id, "strategy": m.strategy,
        "strategy_label": STRATEGIES.get(m.strategy), "message_type": m.message_type,
        "message_type_label": MESSAGE_TYPES.get(m.message_type), "content": m.content, "facts_used": m.facts_used,
        "generator": m.generator, "quality_warnings": m.quality_warnings, "status": m.status, "sent_at": iso(m.sent_at),
        "outcome": m.outcome, "created_at": iso(m.created_at), "chars": len(m.content),
    }


def event_dict(e: OutreachEvent) -> dict[str, Any]:
    return {"id": e.id, "company_id": e.company_id, "contact_id": e.contact_id, "message_id": e.message_id,
            "event_type": e.event_type, "strategy": e.strategy, "occurred_at": iso(e.occurred_at), "notes": e.notes}


def task_dict(t: FollowUpTask, with_company: bool = False) -> dict[str, Any]:
    d = {"id": t.id, "company_id": t.company_id, "contact_id": t.contact_id, "task_type": t.task_type, "title": t.title,
         "due_at": iso(t.due_at), "status": t.status, "sequence_number": t.sequence_number, "reason": t.reason,
         "completed_at": iso(t.completed_at), "cancelled_reason": t.cancelled_reason,
         "overdue": t.status == "open" and t.due_at < datetime.utcnow()}
    if with_company and t.company:
        d["company_name"] = t.company.name
        d["contact_name"] = t.contact.name if t.contact else None
        d["linkedin_url"] = t.contact.linkedin_url if t.contact else None
    return d


def job_dict(j: AutomationJob) -> dict[str, Any]:
    return {"id": j.id, "job_type": j.job_type, "label": JOB_LABELS.get(j.job_type, j.job_type), "payload": j.payload,
            "status": j.status, "priority": j.priority, "attempts": j.attempts, "max_attempts": j.max_attempts,
            "trigger": j.trigger, "parent_id": j.parent_id, "run_after": iso(j.run_after), "created_at": iso(j.created_at),
            "started_at": iso(j.started_at), "finished_at": iso(j.finished_at), "result": j.result,
            "last_error": (j.last_error or "")[:1500] or None, "log": j.log or []}


def suppression_dict(s: SuppressionEntry) -> dict[str, Any]:
    return {"id": s.id, "company_id": s.company_id, "domain": s.domain, "ico": s.ico, "email": s.email,
            "linkedin_url": s.linkedin_url, "name": s.name, "reason": s.reason, "note": s.note, "created_at": iso(s.created_at)}


def hero_screenshot(db: Session, company: Company) -> dict[str, Any] | None:
    a = latest_audit(db, company)
    if not a or not a.screenshots:
        return None
    for dev in ("desktop", "mobile"):
        for s in a.screenshots:
            if s["page"] == "home" and s["device"] == dev:
                return {"url": screenshot_url(s.get("fold_path") or s["path"]), "full_url": screenshot_url(s["path"]), "device": dev}
    return None


def company_summary(db: Session, c: Company, score: LeadScore | None = None) -> dict[str, Any]:
    seg = get_segment(c.segment_key)
    score = score if score is not None else current_score(db, c.id)
    return {
        "id": c.id, "name": c.name, "segment_key": c.segment_key, "segment_label": seg.label if seg else None,
        "tier": c.tier, "city": c.city, "region_code": c.region_code,
        "region_name": REGION_BY_CODE[c.region_code].name if c.region_code in REGION_BY_CODE else None,
        "country": c.country, "website_url": c.website_url, "domain": c.domain, "status": c.status,
        "disqualified_reason": c.disqualified_reason, "ico": c.ico,
        "opportunity_score": score.opportunity_score if score else None,
        "confidence_score": score.confidence_score if score else None,
        "category": score.category if score else None,
        "category_label": CATEGORY_LABELS.get(score.category or "", None) if score else None,
        "design_gap": score.design_gap if score else None,
        "commercial_potential": score.commercial_potential if score else None,
        "buying_readiness": score.buying_readiness if score else None,
        "website_quality": score.website_quality if score else None,
        "website_quality_basis": score.website_quality_basis if score else None,
        "outreach_reason": score.outreach_reason if score else None,
        "last_analyzed_at": iso(c.last_analyzed_at), "first_seen_at": iso(c.first_seen_at), "times_seen": c.times_seen,
        "campaign_id": c.campaign_id,
    }


def company_detail(db: Session, c: Company) -> dict[str, Any]:
    w = latest_website(c)
    a = latest_audit(db, c)
    va = latest_visual(db, c)
    score = current_score(db, c.id)
    contact = best_contact(c)
    msgs = db.scalars(select(OutreachMessage).where(OutreachMessage.company_id == c.id, OutreachMessage.status != "archived")
                      .order_by(OutreachMessage.id.desc())).all()
    events = db.scalars(select(OutreachEvent).where(OutreachEvent.company_id == c.id).order_by(OutreachEvent.occurred_at.desc())).all()
    tasks = db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == c.id).order_by(FollowUpTask.due_at.desc())).all()
    history = db.scalars(select(LeadScore).where(LeadScore.company_id == c.id).order_by(LeadScore.id.desc()).limit(10)).all()
    visual = None
    if va:
        meta = next((x for x in va.criteria or [] if x.get("key") == "_meta"), {})
        visual = {"id": va.id, "status": va.status, "provider": va.provider, "model": va.model, "visual_score": va.visual_score,
                  "confidence": va.confidence, "criteria": [x for x in va.criteria or [] if x.get("key") != "_meta"],
                  "summary": va.summary, "strengths": va.strengths, "top_issues": va.top_issues, "error": va.error,
                  "is_expert_estimate": va.is_expert_estimate, "design_era": meta.get("design_era"),
                  "business_impression": meta.get("business_impression"), "created_at": iso(va.created_at)}
    ex = (w.extracted or {}) if w else {}
    return {
        **company_summary(db, c, score),
        "legal_name": c.legal_name, "legal_form": c.legal_form, "founded_on": c.founded_on, "registry_status": c.registry_status,
        "registered_capital": c.registered_capital, "nace_codes": c.nace_codes,
        "street": c.street, "postcode": c.postcode, "lat": c.lat, "lon": c.lon, "phone": c.phone, "email": c.email,
        "social_links": c.social_links, "opening_hours": c.opening_hours, "notes": c.notes,
        "sources": [{"source": s.data_source.name, "key": s.data_source.key, "external_id": s.external_id,
                     "url": s.source_url, "fetched_at": iso(s.fetched_at)} for s in c.sources],
        "website": None if not w else {
            "url": w.url, "final_url": w.final_url, "reachable": w.reachable, "status_code": w.status_code,
            "robots_allowed": w.robots_allowed, "https": w.https, "cms": w.cms, "technologies": w.technologies,
            "title": w.title, "meta_description": w.meta_description, "discovered_pages": w.discovered_pages,
            "last_crawled_at": iso(w.last_crawled_at), "last_error": w.last_error,
            "facts": {k: ex.get(k) for k in ("copyright_year", "emails", "phones", "icos", "socials", "price_count", "price_median",
                                             "portfolio_image_count", "has_booking", "has_eshop", "has_contact_form",
                                             "has_language_switch", "since_year", "years_experience", "latest_date",
                                             "pages_crawled", "total_word_count", "quality", "quality_snippets", "persons", "h1")},
        },
        "audit": None if not a else {
            "id": a.id, "technical_score": a.technical_score, "issues": a.issues, "complete": a.complete,
            "incomplete_reasons": a.incomplete_reasons, "metrics": a.metrics, "created_at": iso(a.created_at),
            "screenshots": [{**s, "url": screenshot_url(s["path"]), "fold_url": screenshot_url(s.get("fold_path"))} for s in a.screenshots or []],
        },
        "visual": visual,
        "signals": [{"id": s.id, "signal_type": s.signal_type, "category": s.category, "description": s.description,
                     "evidence": s.evidence, "source_url": s.source_url, "strength": s.strength, "detected_at": iso(s.detected_at)}
                    for s in sorted(c.signals, key=lambda x: -x.strength)],
        "score": score_dict(score),
        "score_history": [{"opportunity_score": h.opportunity_score, "confidence_score": h.confidence_score,
                           "category": h.category, "computed_at": iso(h.created_at)} for h in history],
        "contacts": [contact_dict(x) for x in c.contacts],
        "best_contact_id": contact.id if contact else None,
        "linkedin": {"links": linkedin_links(c, contact), "queries": search_queries(c)},
        "messages": [message_dict(m) for m in msgs],
        "events": [event_dict(e) for e in events],
        "tasks": [task_dict(t) for t in tasks],
        "hero_screenshot": hero_screenshot(db, c),
    }
