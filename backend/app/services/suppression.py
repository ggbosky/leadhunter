"""Suppression list (Do Not Contact)."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Company, Contact, FollowUpTask, SuppressionEntry, utcnow
from .normalize import normalize_linkedin

SUPPRESSION_REASONS = {
    "refused": "Výslovně odmítl kontaktování",
    "requested_removal": "Požádal o výmaz údajů",
    "manual": "Ručně přidáno",
    "competitor": "Konkurence / partner",
    "existing_client": "Stávající klient",
}


def find_suppression(db: Session, company: Company | None = None, contact: Contact | None = None) -> SuppressionEntry | None:
    conds = []
    if company is not None:
        conds.append(SuppressionEntry.company_id == company.id)
        if company.domain:
            conds.append(SuppressionEntry.domain == company.domain)
        if company.ico:
            conds.append(SuppressionEntry.ico == company.ico)
        if company.email:
            conds.append(SuppressionEntry.email == company.email.lower())
    if contact is not None:
        if contact.email:
            conds.append(SuppressionEntry.email == contact.email.lower())
        li = normalize_linkedin(contact.linkedin_url)
        if li:
            conds.append(SuppressionEntry.linkedin_url == li)
    if not conds:
        return None
    return db.scalar(select(SuppressionEntry).where(or_(*conds)).limit(1))


def suppress_company(db: Session, company: Company, reason: str, note: str | None = None,
                     contact: Contact | None = None) -> SuppressionEntry:
    """Přidá firmu na Do Not Contact, zruší otevřené follow-upy a vyřadí lead."""
    entry = find_suppression(db, company=company)
    if entry is None:
        entry = SuppressionEntry(
            company_id=company.id, domain=company.domain, ico=company.ico,
            email=(company.email or "").lower() or None, name=company.name, reason=reason, note=note,
            linkedin_url=normalize_linkedin(contact.linkedin_url) if contact else None,
        )
        db.add(entry)
    company.status = "disqualified"
    company.disqualified_reason = "do_not_contact"
    for c in company.contacts:
        c.do_not_contact = True
        c.next_step = None
        c.next_step_at = None
    for t in db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == company.id, FollowUpTask.status == "open")):
        t.status = "cancelled"
        t.cancelled_reason = "Do Not Contact"
        t.completed_at = utcnow()
    db.flush()
    return entry
