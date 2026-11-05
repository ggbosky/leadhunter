"""API: leady, firmy, kontakty, zprávy, outreach."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs.queue import enqueue
from ..models import (
    BuyingSignal,
    Company,
    CompanySource,
    Contact,
    FollowUpTask,
    LeadScore,
    OutreachEvent,
    OutreachMessage,
    utcnow,
)
from ..segments import get_segment
from ..services.discovery import import_rows
from ..services.linkedin import best_contact
from ..services.messages import STRATEGIES, generate_message_set
from ..services.normalize import ensure_url, normalize_domain, normalize_linkedin, normalize_name
from ..services.outreach import (
    OutreachBlocked,
    mark_connected,
    mark_contacted,
    mark_not_interested,
    record_reply,
    schedule_follow_up,
)
from ..services.pipeline import CONTACTED_STATUSES, analyze_company, score_company
from ..services.signals import _fp
from ..services.suppression import find_suppression
from .serializers import company_detail, company_summary, contact_dict, message_dict, hero_screenshot

router = APIRouter()


def _company(db: Session, cid: int) -> Company:
    c = db.get(Company, cid)
    if c is None:
        raise HTTPException(404, "Firma nenalezena")
    return c


# ---------------------------------------------------------------------------
# Leady
# ---------------------------------------------------------------------------
@router.get("/leads")
def list_leads(
    db: Session = Depends(get_db),
    search: str | None = None,
    segment: str | None = None,
    tier: int | None = None,
    region: str | None = None,
    status: str | None = None,
    category: str | None = None,
    min_score: float | None = None,
    has_website: bool | None = None,
    analyzed: bool | None = None,
    sort: str = "score",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(Company, LeadScore).outerjoin(LeadScore, and_(LeadScore.company_id == Company.id, LeadScore.is_current.is_(True)))
    if search:
        like = f"%{normalize_name(search)}%"
        q = q.where(or_(Company.normalized_name.like(like), Company.domain.like(f"%{search.lower()}%"), Company.ico == search.strip()))
    if segment:
        q = q.where(Company.segment_key == segment)
    if tier:
        q = q.where(Company.tier == tier)
    if region:
        q = q.where(Company.region_code == region)
    if status:
        q = q.where(Company.status.in_(status.split(",")))
    if category:
        q = q.where(LeadScore.category.in_(category.split(",")))
    if min_score is not None:
        q = q.where(LeadScore.opportunity_score >= min_score)
    if has_website is not None:
        q = q.where(Company.website_url.is_not(None) if has_website else Company.website_url.is_(None))
    if analyzed is not None:
        q = q.where(Company.last_analyzed_at.is_not(None) if analyzed else Company.last_analyzed_at.is_(None))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    order = {
        "score": (LeadScore.opportunity_score.is_(None), LeadScore.opportunity_score.desc(), Company.id.desc()),
        "newest": (Company.first_seen_at.desc(),),
        "name": (Company.normalized_name,),
        "design_gap": (LeadScore.design_gap.is_(None), LeadScore.design_gap.desc()),
        "confidence": (LeadScore.confidence_score.is_(None), LeadScore.confidence_score.desc()),
        "analyzed": (Company.last_analyzed_at.is_(None), Company.last_analyzed_at.desc()),
    }.get(sort, (LeadScore.opportunity_score.desc(),))
    rows = db.execute(q.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for c, s in rows:
        d = company_summary(db, c, s)
        d["hero_screenshot"] = hero_screenshot(db, c)
        items.append(d)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    website: str | None = None
    city: str | None = None
    segment_key: str | None = None
    ico: str | None = None
    email: str | None = None
    phone: str | None = None
    region_code: str | None = None
    country: str = "CZ"
    analyze: bool = True


@router.post("/companies")
def create_company(body: CompanyCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    stats = import_rows(db, [body.model_dump()], segment_key=body.segment_key)
    if stats.errors:
        raise HTTPException(400, "; ".join(stats.errors))
    cid = stats.company_ids[0] if stats.company_ids else None
    if cid is None:
        dom = normalize_domain(body.website) if body.website else None
        c = db.scalar(select(Company).where(Company.domain == dom)) if dom else None
        if c is None:
            raise HTTPException(409, "Firma už existuje nebo ji nelze uložit")
        cid = c.id
    job = None
    if body.analyze:
        job = enqueue(db, "analyze", {"company_id": cid}, priority=20, dedupe_key=f"analyze:{cid}")
        db.commit()
    return {"company_id": cid, "created": bool(stats.created), "job_id": job.id if job else None}


@router.post("/companies/import")
async def import_companies(file: UploadFile = File(...), segment_key: str | None = None, analyze: bool = False,
                           db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = (await file.read())[:5_000_000]
    text = raw.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text), dialect=dialect)]
    stats = import_rows(db, rows, segment_key=segment_key)
    jobs = 0
    if analyze:
        for cid in stats.company_ids:
            enqueue(db, "analyze", {"company_id": cid}, priority=60, dedupe_key=f"analyze:{cid}")
            jobs += 1
        db.commit()
    return {**stats.to_dict(), "analyze_jobs": jobs}


@router.get("/companies/{cid}")
def get_company(cid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return company_detail(db, _company(db, cid))


class CompanyPatch(BaseModel):
    name: str | None = None
    segment_key: str | None = None
    status: Literal["new", "analyzed", "qualified", "contacted", "replied", "meeting", "won", "lost", "disqualified"] | None = None
    notes: str | None = None
    website_url: str | None = None
    city: str | None = None
    region_code: str | None = None
    email: str | None = None
    phone: str | None = None
    campaign_id: int | None = None
    disqualified_reason: str | None = None


@router.patch("/companies/{cid}")
def patch_company(cid: int, body: CompanyPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    data = body.model_dump(exclude_unset=True)
    if "segment_key" in data:
        seg = get_segment(data["segment_key"])
        if data["segment_key"] and not seg:
            raise HTTPException(400, "Neznámý segment")
        c.segment_key = data.pop("segment_key")
        c.tier = seg.tier if seg else None
    if "website_url" in data:
        url = ensure_url(data.pop("website_url"))
        dom = normalize_domain(url) if url else None
        if dom and db.scalar(select(Company).where(Company.domain == dom, Company.id != c.id)):
            raise HTTPException(409, "Jiná firma už má tuto doménu (možná duplicita)")
        c.website_url, c.domain = url, dom
    if "name" in data and data["name"]:
        c.normalized_name = normalize_name(data["name"])
    if data.get("status") == "disqualified" and not data.get("disqualified_reason"):
        data["disqualified_reason"] = "manual"
    for k, v in data.items():
        setattr(c, k, v)
    if c.last_analyzed_at:
        score_company(db, c)
    db.commit()
    return company_detail(db, c)


@router.delete("/companies/{cid}")
def delete_company(cid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    db.delete(c)
    db.commit()
    return {"deleted": cid}


@router.post("/companies/{cid}/analyze")
def analyze(cid: int, sync: bool = False, screenshots: bool = True, vision: bool = True, db: Session = Depends(get_db)) -> dict[str, Any]:
    _company(db, cid)
    if sync:
        res = analyze_company(db, cid, screenshots=screenshots, vision=vision)
        return {"result": res, "company": company_detail(db, _company(db, cid))}
    job = enqueue(db, "analyze", {"company_id": cid, "screenshots": screenshots, "vision": vision}, priority=20, dedupe_key=f"analyze:{cid}")
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/companies/{cid}/rescore")
def rescore(cid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    score_company(db, c)
    db.commit()
    return company_detail(db, c)


class MergeBody(BaseModel):
    duplicate_id: int


@router.post("/companies/{cid}/merge")
def merge(cid: int, body: MergeBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Sloučí duplicitní záznam do této firmy (kontakty, zdroje, zprávy, události, úkoly)."""
    target = _company(db, cid)
    dup = _company(db, body.duplicate_id)
    if dup.id == target.id:
        raise HTTPException(400, "Nelze sloučit firmu samu se sebou")
    for model in (Contact, OutreachMessage, OutreachEvent, FollowUpTask):
        for row in db.scalars(select(model).where(model.company_id == dup.id)):
            row.company_id = target.id
    for src in db.scalars(select(CompanySource).where(CompanySource.company_id == dup.id)):
        src.company_id = target.id
    for f in ("ico", "domain", "website_url", "email", "phone", "street", "city", "postcode", "segment_key", "legal_form", "founded_on"):
        if not getattr(target, f) and getattr(dup, f):
            val = getattr(dup, f)
            if f in ("ico", "domain"):  # unikátní sloupce – nejdřív uvolnit
                setattr(dup, f, None)
                db.flush()
            setattr(target, f, val)
    target.times_seen += dup.times_seen
    db.flush()
    db.delete(dup)
    db.commit()
    return company_detail(db, target)


class SignalCreate(BaseModel):
    signal_type: str
    description: str
    evidence: str | None = None
    source_url: str | None = None
    strength: float = Field(0.5, ge=0, le=1)


@router.post("/companies/{cid}/signals")
def add_signal(cid: int, body: SignalCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    db.add(BuyingSignal(company_id=c.id, category="manual", fingerprint=_fp("manual", body.description, utcnow().isoformat()),
                        **body.model_dump()))
    db.flush()
    score_company(db, c)
    db.commit()
    return company_detail(db, c)


@router.delete("/signals/{sid}")
def delete_signal(sid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.get(BuyingSignal, sid)
    if not s:
        raise HTTPException(404, "Signál nenalezen")
    c = db.get(Company, s.company_id)
    db.delete(s)
    db.flush()
    score_company(db, c)
    db.commit()
    return {"deleted": sid}


# ---------------------------------------------------------------------------
# Kontakty
# ---------------------------------------------------------------------------
class ContactBody(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    is_decision_maker: bool | None = None
    is_primary: bool | None = None
    verified: bool | None = None
    connection_status: Literal["none", "request_sent", "connected", "ignored", "not_on_linkedin"] | None = None
    next_step: str | None = None
    next_step_at: datetime | None = None
    notes: str | None = None


def _apply_contact(db: Session, c: Contact, data: dict) -> None:
    if "linkedin_url" in data and data["linkedin_url"]:
        li = normalize_linkedin(data["linkedin_url"])
        if not li:
            raise HTTPException(400, "Neplatná LinkedIn URL")
        data["linkedin_url"] = li
    if data.get("is_primary"):
        for other in c.company.contacts if c.company else []:
            if other.id != c.id:
                other.is_primary = False
    for k, v in data.items():
        setattr(c, k, v)


@router.post("/companies/{cid}/contacts")
def add_contact(cid: int, body: ContactBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = _company(db, cid)
    if not body.name:
        raise HTTPException(400, "Jméno je povinné")
    c = Contact(company_id=company.id, name=body.name, source="manual", verified=True)
    db.add(c)
    company.contacts.append(c)
    data = body.model_dump(exclude_unset=True)
    data.setdefault("is_decision_maker", True)
    _apply_contact(db, c, data)
    if find_suppression(db, contact=c):
        c.do_not_contact = True
    db.flush()
    score_company(db, company)
    db.commit()
    return contact_dict(c)


@router.patch("/contacts/{contact_id}")
def patch_contact(contact_id: int, body: ContactBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "Kontakt nenalezen")
    _apply_contact(db, c, body.model_dump(exclude_unset=True))
    if body.connection_status == "connected":
        mark_connected(db, c.company, c)
    db.flush()
    score_company(db, c.company)
    db.commit()
    return contact_dict(c)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "Kontakt nenalezen")
    company = c.company
    db.delete(c)
    db.flush()
    db.refresh(company)
    score_company(db, company)
    db.commit()
    return {"deleted": contact_id}


# ---------------------------------------------------------------------------
# Zprávy
# ---------------------------------------------------------------------------
class GenerateBody(BaseModel):
    strategy: str | None = "auto"
    contact_id: int | None = None
    use_llm: bool = True


@router.post("/companies/{cid}/messages/generate")
def generate(cid: int, body: GenerateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    if find_suppression(db, company=c):
        raise HTTPException(409, "Firma je na seznamu Do Not Contact")
    if body.strategy and body.strategy != "auto" and body.strategy.upper() not in STRATEGIES:
        raise HTTPException(400, "Neplatná strategie")
    contact = db.get(Contact, body.contact_id) if body.contact_id else None
    msgs = generate_message_set(db, c, strategy=body.strategy, contact=contact, use_llm=body.use_llm)
    db.commit()
    return {"messages": [message_dict(m) for m in msgs]}


class MessagePatch(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


@router.patch("/messages/{mid}")
def patch_message(mid: int, body: MessagePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(OutreachMessage, mid)
    if not m:
        raise HTTPException(404, "Zpráva nenalezena")
    m.content = body.content
    if "(upraveno)" not in m.generator:
        m.generator = f"{m.generator} (upraveno)"
    db.commit()
    return message_dict(m)


# ---------------------------------------------------------------------------
# Outreach workspace
# ---------------------------------------------------------------------------
@router.get("/outreach/queue")
def outreach_queue(db: Session = Depends(get_db), min_score: float = 0, include_without_messages: bool = True,
                   segment: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Fronta leadů k oslovení: kvalifikované, neoslovené, mimo DNC, seřazené podle skóre."""
    has_msgs = select(OutreachMessage.company_id).where(OutreachMessage.status == "draft")
    q = (select(Company, LeadScore).join(LeadScore, and_(LeadScore.company_id == Company.id, LeadScore.is_current.is_(True)))
         .where(Company.status.in_(["qualified", "analyzed"]), LeadScore.opportunity_score.is_not(None),
                LeadScore.opportunity_score >= min_score))
    if not include_without_messages:
        q = q.where(Company.id.in_(has_msgs))
    if segment:
        q = q.where(Company.segment_key == segment)
    rows = db.execute(q.order_by(Company.id.in_(has_msgs).desc(), LeadScore.opportunity_score.desc()).limit(limit)).all()
    drafted = set(db.scalars(has_msgs).all())
    items = []
    for c, s in rows:
        d = company_summary(db, c, s)
        d["has_messages"] = c.id in drafted
        bc = best_contact(c)
        d["contact_name"] = bc.name if bc else None
        d["has_linkedin"] = bool(bc and bc.linkedin_url)
        items.append(d)
    # navíc úkoly po termínu (follow-upy) – zobrazí se v sekci follow-upů
    return {"items": items, "total": len(items)}


class ContactedBody(BaseModel):
    message_id: int | None = None
    contact_id: int | None = None
    kind: Literal["connection_requested", "message_sent", "follow_up_sent"] = "message_sent"
    notes: str | None = None
    follow_up_days: int | None = Field(None, ge=0, le=90)


def _contact_for(db: Session, company: Company, contact_id: int | None) -> Contact | None:
    if contact_id:
        c = db.get(Contact, contact_id)
        if not c or c.company_id != company.id:
            raise HTTPException(400, "Kontakt nepatří k firmě")
        return c
    return best_contact(company)


@router.post("/companies/{cid}/outreach/contacted")
def contacted(cid: int, body: ContactedBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    msg = db.get(OutreachMessage, body.message_id) if body.message_id else None
    if msg and msg.company_id != c.id:
        raise HTTPException(400, "Zpráva nepatří k firmě")
    try:
        res = mark_contacted(db, c, contact=_contact_for(db, c, body.contact_id), message=msg, kind=body.kind,
                             notes=body.notes, follow_up_days=body.follow_up_days)
    except OutreachBlocked as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return res


class ReplyBody(BaseModel):
    outcome: Literal["replied_positive", "replied_neutral", "replied_negative", "meeting", "won", "lost"]
    contact_id: int | None = None
    notes: str | None = None
    next_step: str | None = None
    next_step_at: datetime | None = None


@router.post("/companies/{cid}/outreach/reply")
def reply(cid: int, body: ReplyBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    record_reply(db, c, outcome=body.outcome, contact=_contact_for(db, c, body.contact_id), notes=body.notes,
                 next_step=body.next_step, next_step_at=body.next_step_at)
    db.commit()
    return {"status": c.status}


class NotInterestedBody(BaseModel):
    explicit_refusal: bool = True
    contact_id: int | None = None
    notes: str | None = None


@router.post("/companies/{cid}/outreach/not-interested")
def not_interested(cid: int, body: NotInterestedBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    mark_not_interested(db, c, contact=_contact_for(db, c, body.contact_id), explicit_refusal=body.explicit_refusal, notes=body.notes)
    db.commit()
    return {"status": c.status, "suppressed": body.explicit_refusal}


class FollowUpBody(BaseModel):
    days: int | None = Field(None, ge=0, le=180)
    due_at: datetime | None = None
    title: str | None = None
    contact_id: int | None = None


@router.post("/companies/{cid}/outreach/follow-up")
def follow_up(cid: int, body: FollowUpBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _company(db, cid)
    try:
        task = schedule_follow_up(db, c, contact=_contact_for(db, c, body.contact_id), days=body.days, due_at=body.due_at,
                                  title=body.title, task_type="follow_up" if not body.title else "custom")
    except OutreachBlocked as exc:
        raise HTTPException(409, str(exc)) from exc
    if task is None:
        raise HTTPException(409, "Limit follow-upů je vyčerpán – další připomínky nejsou vhodné")
    db.commit()
    return {"task_id": task.id, "due_at": task.due_at.isoformat() + "Z"}
