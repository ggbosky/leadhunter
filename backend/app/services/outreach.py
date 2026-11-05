"""Outreach workflow a Smart Follow-up System.

Vše probíhá ručně (uživatel odešle zprávu na LinkedInu sám) – aplikace jen
eviduje události, plánuje připomínky a hlídá pravidla:
- po odpovědi / odmítnutí se další připomínky zastaví,
- výslovné odmítnutí → Do Not Contact,
- maximální počet follow-upů je konfigurovatelný.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, Contact, FollowUpTask, OutreachEvent, OutreachMessage, utcnow
from ..settings_store import get_setting
from .suppression import find_suppression, suppress_company


class OutreachBlocked(Exception):
    pass


def _ensure_contactable(db: Session, company: Company, contact: Contact | None) -> None:
    entry = find_suppression(db, company=company, contact=contact)
    if entry is not None:
        raise OutreachBlocked(f"Firma/kontakt je na Do Not Contact ({entry.reason})")
    if contact is not None and contact.do_not_contact:
        raise OutreachBlocked("Kontakt je označen jako Do Not Contact")


def cancel_open_tasks(db: Session, company: Company, reason: str) -> int:
    n = 0
    for t in db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == company.id, FollowUpTask.status == "open")):
        t.status = "cancelled"
        t.cancelled_reason = reason
        t.completed_at = utcnow()
        n += 1
    return n


def log_event(db: Session, company: Company, event_type: str, *, contact: Contact | None = None,
              message: OutreachMessage | None = None, notes: str | None = None, occurred_at: datetime | None = None) -> OutreachEvent:
    ev = OutreachEvent(company_id=company.id, contact_id=contact.id if contact else None,
                       message_id=message.id if message else None, event_type=event_type,
                       strategy=message.strategy if message else None, notes=notes, occurred_at=occurred_at or utcnow())
    db.add(ev)
    db.flush()
    return ev


def schedule_follow_up(db: Session, company: Company, *, contact: Contact | None = None, days: int | None = None,
                       due_at: datetime | None = None, title: str | None = None, task_type: str = "follow_up",
                       reason: str | None = None) -> FollowUpTask | None:
    _ensure_contactable(db, company, contact)
    cfg = get_setting(db, "followup")
    previous = db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == company.id, FollowUpTask.task_type == "follow_up")).all()
    seq = len(previous) + 1
    if task_type == "follow_up" and seq > int(cfg["max_followups"]) + 1:
        return None  # limit follow-upů vyčerpán – nevnucujeme se
    if due_at is None:
        d = days if days is not None else (cfg["first_followup_days"] if seq <= 1 else cfg["second_followup_days"])
        due_at = utcnow() + timedelta(days=int(d))
    # jen jeden otevřený follow-up na firmu
    for t in db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == company.id, FollowUpTask.status == "open",
                                                   FollowUpTask.task_type == task_type)):
        t.status = "cancelled"
        t.cancelled_reason = "Nahrazeno novým termínem"
        t.completed_at = utcnow()
    task = FollowUpTask(company_id=company.id, contact_id=contact.id if contact else None, task_type=task_type,
                        title=title or (f"Follow-up č. {seq - 1 if seq > 1 else 1}: {company.name}" if task_type == "follow_up"
                                        else f"Zkontrolovat přijetí spojení: {company.name}"),
                        due_at=due_at, sequence_number=seq, reason=reason, status="open")
    db.add(task)
    if contact:
        contact.next_step = task.title
        contact.next_step_at = due_at
    db.flush()
    return task


def mark_contacted(db: Session, company: Company, *, contact: Contact | None = None, message: OutreachMessage | None = None,
                   kind: str = "message_sent", notes: str | None = None, follow_up_days: int | None = None) -> dict:
    """kind: connection_requested | message_sent | follow_up_sent"""
    _ensure_contactable(db, company, contact)
    now = utcnow()
    cfg = get_setting(db, "followup")
    if message is not None:
        message.status = "sent"
        message.sent_at = now
        message.outcome = "pending"
        # ostatní koncepty stejné sady zůstávají jako koncepty pro další kroky
    if contact is not None:
        contact.first_contacted_at = contact.first_contacted_at or now
        contact.last_contacted_at = now
        contact.contact_attempts += 1
        if kind == "connection_requested" and contact.connection_status == "none":
            contact.connection_status = "request_sent"
    if company.status not in ("replied", "meeting", "won"):
        company.status = "contacted"
    ev = log_event(db, company, kind, contact=contact, message=message, notes=notes)
    if kind == "connection_requested":
        task = schedule_follow_up(db, company, contact=contact, days=follow_up_days or cfg["connection_check_days"],
                                  task_type="check_connection", reason="Ověřit, zda bylo spojení přijato, a poslat první zprávu")
    else:
        task = schedule_follow_up(db, company, contact=contact, days=follow_up_days, task_type="follow_up",
                                  reason="Bez odpovědi – zdvořile se připomenout")
    db.flush()
    return {"event_id": ev.id, "task_id": task.id if task else None, "follow_up_limit_reached": task is None}


def mark_connected(db: Session, company: Company, contact: Contact) -> None:
    contact.connection_status = "connected"
    log_event(db, company, "connected", contact=contact)
    for t in db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == company.id, FollowUpTask.status == "open",
                                                   FollowUpTask.task_type == "check_connection")):
        t.status = "done"
        t.completed_at = utcnow()
    schedule_follow_up(db, company, contact=contact, days=0, task_type="custom",
                       title=f"Poslat první zprávu: {company.name}", reason="Spojení přijato")


def record_reply(db: Session, company: Company, *, outcome: str, contact: Contact | None = None, notes: str | None = None,
                 next_step: str | None = None, next_step_at: datetime | None = None) -> None:
    """outcome: replied_positive | replied_neutral | replied_negative | meeting | won | lost"""
    now = utcnow()
    cancel_open_tasks(db, company, "Klient odpověděl")
    last_msg = db.scalar(select(OutreachMessage).where(OutreachMessage.company_id == company.id, OutreachMessage.status == "sent")
                         .order_by(OutreachMessage.sent_at.desc()).limit(1))
    if last_msg:
        last_msg.outcome = outcome
        last_msg.outcome_at = now
    if contact:
        contact.replied_at = now
        contact.next_step = next_step
        contact.next_step_at = next_step_at
    status_map = {"replied_positive": "replied", "replied_neutral": "replied", "replied_negative": "lost",
                  "meeting": "meeting", "won": "won", "lost": "lost"}
    company.status = status_map.get(outcome, "replied")
    event_map = {"meeting": "meeting", "won": "won", "lost": "lost"}
    log_event(db, company, event_map.get(outcome, "replied"), contact=contact, message=last_msg, notes=notes)
    if next_step_at and outcome in ("replied_positive", "replied_neutral", "meeting"):
        db.add(FollowUpTask(company_id=company.id, contact_id=contact.id if contact else None, task_type="custom",
                            title=next_step or f"Další krok: {company.name}", due_at=next_step_at, status="open",
                            reason="Domluvený další krok"))
    db.flush()


def mark_not_interested(db: Session, company: Company, *, contact: Contact | None = None, explicit_refusal: bool = True,
                        notes: str | None = None) -> None:
    """Nezájem. Výslovné odmítnutí → Do Not Contact."""
    cancel_open_tasks(db, company, "Nezájem")
    last_msg = db.scalar(select(OutreachMessage).where(OutreachMessage.company_id == company.id, OutreachMessage.status == "sent")
                         .order_by(OutreachMessage.sent_at.desc()).limit(1))
    if last_msg:
        last_msg.outcome = "replied_negative"
        last_msg.outcome_at = utcnow()
    log_event(db, company, "not_interested", contact=contact, message=last_msg, notes=notes)
    if explicit_refusal:
        suppress_company(db, company, "refused", note=notes, contact=contact)
        log_event(db, company, "do_not_contact", contact=contact, notes="Přidáno na Do Not Contact po odmítnutí")
    else:
        company.status = "lost" if company.status in ("contacted", "replied") else "disqualified"
        if company.status == "disqualified":
            company.disqualified_reason = "manual"
    db.flush()


def complete_task(db: Session, task: FollowUpTask, *, sent: bool = False) -> FollowUpTask | None:
    """Dokončí úkol. Pokud šlo o odeslaný follow-up, naplánuje další (do limitu)."""
    task.status = "done"
    task.completed_at = utcnow()
    company = db.get(Company, task.company_id)
    contact = db.get(Contact, task.contact_id) if task.contact_id else None
    nxt = None
    if sent and company is not None and task.task_type == "follow_up":
        log_event(db, company, "follow_up_sent", contact=contact)
        if contact:
            contact.contact_attempts += 1
            contact.last_contacted_at = utcnow()
        try:
            nxt = schedule_follow_up(db, company, contact=contact)
        except OutreachBlocked:
            nxt = None
    db.flush()
    return nxt


def due_tasks(db: Session, until: datetime | None = None) -> list[FollowUpTask]:
    until = until or utcnow()
    return list(db.scalars(select(FollowUpTask).where(FollowUpTask.status == "open", FollowUpTask.due_at <= until)
                           .order_by(FollowUpTask.due_at)))
