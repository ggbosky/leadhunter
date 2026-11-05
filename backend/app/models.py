"""Datový model CRM a automatizace.

Všechny entity mají created_at / updated_at. Navrženo pro SQLite s možností
migrace na PostgreSQL (žádné SQLite-specifické typy, JSON přes sqlalchemy.JSON).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Zdroje dat
# ---------------------------------------------------------------------------
class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # map | registry | search | manual | website
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    access_policy: Mapped[Optional[str]] = mapped_column(Text)  # popis povoleného přístupu / licence
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_status: Mapped[Optional[str]] = mapped_column(String(32))  # ok | unavailable | not_configured | error
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    segment_keys: Mapped[list] = mapped_column(JSON, default=list)
    region_codes: Mapped[list] = mapped_column(JSON, default=list)
    default_strategy: Mapped[Optional[str]] = mapped_column(String(2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    companies: Mapped[list["Company"]] = relationship(back_populates="campaign")


# ---------------------------------------------------------------------------
# Firmy a kontakty
# ---------------------------------------------------------------------------
class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_norm_name_city", "normalized_name", "city"),
        Index("ix_companies_status", "status"),
        Index("ix_companies_segment", "segment_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(300))
    ico: Mapped[Optional[str]] = mapped_column(String(16), unique=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(100))
    founded_on: Mapped[Optional[str]] = mapped_column(String(10))  # ISO datum vzniku z ARES
    registry_status: Mapped[Optional[str]] = mapped_column(String(64))
    nace_codes: Mapped[list] = mapped_column(JSON, default=list)
    registered_capital: Mapped[Optional[int]] = mapped_column(Integer)

    segment_key: Mapped[Optional[str]] = mapped_column(String(64))
    tier: Mapped[Optional[int]] = mapped_column(Integer)

    country: Mapped[str] = mapped_column(String(2), default="CZ", nullable=False)
    region_code: Mapped[Optional[str]] = mapped_column(String(16))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    street: Mapped[Optional[str]] = mapped_column(String(200))
    postcode: Mapped[Optional[str]] = mapped_column(String(16))
    normalized_address: Mapped[Optional[str]] = mapped_column(String(400), index=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)

    phone: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    website_url: Mapped[Optional[str]] = mapped_column(String(500))
    domain: Mapped[Optional[str]] = mapped_column(String(253), unique=True)
    social_links: Mapped[dict] = mapped_column(JSON, default=dict)
    opening_hours: Mapped[Optional[str]] = mapped_column(String(300))
    osm_ref: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # pipeline: new -> analyzed -> qualified -> contacted -> replied -> meeting -> won | lost | disqualified
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    disqualified_reason: Mapped[Optional[str]] = mapped_column(String(64))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    times_seen: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    campaign: Mapped[Optional[Campaign]] = relationship(back_populates="companies")

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    websites: Mapped[list["Website"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    sources: Mapped[list["CompanySource"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    signals: Mapped[list["BuyingSignal"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    scores: Mapped[list["LeadScore"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    messages: Mapped[list["OutreachMessage"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    events: Mapped[list["OutreachEvent"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    tasks: Mapped[list["FollowUpTask"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class CompanySource(TimestampMixin, Base):
    """Evidence původu záznamu – z jakého zdroje a pod jakým ID byla firma nalezena."""

    __tablename__ = "company_sources"
    __table_args__ = (UniqueConstraint("data_source_id", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(800))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="sources")
    data_source: Mapped[DataSource] = relationship()


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    is_decision_maker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)  # manual | website | ares_vr
    source_evidence: Mapped[Optional[str]] = mapped_column(Text)
    # none | request_sent | connected | ignored | not_on_linkedin
    connection_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    first_contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_step: Mapped[Optional[str]] = mapped_column(String(300))
    next_step_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="contacts")


# ---------------------------------------------------------------------------
# Weby, audity, vizuální analýzy
# ---------------------------------------------------------------------------
class Website(TimestampMixin, Base):
    __tablename__ = "websites"
    __table_args__ = (UniqueConstraint("company_id", "url", name="uq_website_company_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    final_url: Mapped[Optional[str]] = mapped_column(String(500))
    domain: Mapped[Optional[str]] = mapped_column(String(253))
    reachable: Mapped[Optional[bool]] = mapped_column(Boolean)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    robots_allowed: Mapped[Optional[bool]] = mapped_column(Boolean)
    https: Mapped[Optional[bool]] = mapped_column(Boolean)
    cms: Mapped[Optional[str]] = mapped_column(String(64))
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    meta_description: Mapped[Optional[str]] = mapped_column(Text)
    discovered_pages: Mapped[dict] = mapped_column(JSON, default=dict)  # {services: url, portfolio: url, contact: url}
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)  # výsledky extrakce (e-maily, ceny, signály ...)
    text_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="websites")
    audits: Mapped[list["WebsiteAudit"]] = relationship(back_populates="website", cascade="all, delete-orphan")


class WebsiteAudit(TimestampMixin, Base):
    __tablename__ = "website_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    technical_score: Mapped[Optional[float]] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)  # [{code, title, detail, severity}]
    screenshots: Mapped[list] = mapped_column(JSON, default=list)  # [{page, device, path, url}]
    complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    incomplete_reasons: Mapped[list] = mapped_column(JSON, default=list)

    website: Mapped[Website] = relationship(back_populates="audits")
    visual_analyses: Mapped[list["VisualAnalysis"]] = relationship(back_populates="audit", cascade="all, delete-orphan")


class VisualAnalysis(TimestampMixin, Base):
    __tablename__ = "visual_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("website_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # complete | incomplete | failed
    visual_score: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    top_issues: Mapped[list] = mapped_column(JSON, default=list)
    is_expert_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    raw_response: Mapped[Optional[str]] = mapped_column(Text)

    audit: Mapped[WebsiteAudit] = relationship(back_populates="visual_analyses")


# ---------------------------------------------------------------------------
# Signály, skóre
# ---------------------------------------------------------------------------
class BuyingSignal(TimestampMixin, Base):
    __tablename__ = "buying_signals"
    __table_args__ = (UniqueConstraint("company_id", "signal_type", "fingerprint", name="uq_signal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    # hiring | new_branch | new_service | new_product | rebranding | expansion | active_marketing |
    # investment | young_company | free_builder | outdated_site | eshop_growth
    signal_type: Mapped[str] = mapped_column(String(48), nullable=False)
    category: Mapped[str] = mapped_column(String(16), default="readiness", nullable=False)  # readiness | commercial | quality
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(800))
    strength: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(back_populates="signals")


class LeadScore(TimestampMixin, Base):
    __tablename__ = "lead_scores"
    __table_args__ = (Index("ix_lead_scores_current", "company_id", "is_current"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    category: Mapped[Optional[str]] = mapped_column(String(32))  # priority | strong | potential | low | insufficient
    design_gap: Mapped[Optional[float]] = mapped_column(Float)
    commercial_potential: Mapped[Optional[float]] = mapped_column(Float)
    buying_readiness: Mapped[Optional[float]] = mapped_column(Float)
    service_fit: Mapped[Optional[float]] = mapped_column(Float)
    contactability: Mapped[Optional[float]] = mapped_column(Float)
    business_quality: Mapped[Optional[float]] = mapped_column(Float)
    website_quality: Mapped[Optional[float]] = mapped_column(Float)
    website_quality_basis: Mapped[Optional[str]] = mapped_column(String(32))  # visual | technical | none | no_website
    components: Mapped[dict] = mapped_column(JSON, default=dict)  # důvody pro každou komponentu
    recommended_service: Mapped[Optional[str]] = mapped_column(String(64))
    estimated_budget: Mapped[Optional[dict]] = mapped_column(JSON)
    outreach_reason: Mapped[Optional[str]] = mapped_column(Text)
    disqualification_reasons: Mapped[list] = mapped_column(JSON, default=list)

    company: Mapped[Company] = relationship(back_populates="scores")


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------
class OutreachMessage(TimestampMixin, Base):
    __tablename__ = "outreach_messages"
    __table_args__ = (Index("ix_messages_company_type", "company_id", "message_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(32), default="linkedin", nullable=False)
    strategy: Mapped[str] = mapped_column(String(2), nullable=False)  # A–E
    # connection_request | first_message | follow_up | alternative | pitch
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    facts_used: Mapped[list] = mapped_column(JSON, default=list)
    generator: Mapped[str] = mapped_column(String(100), nullable=False)
    quality_warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft | sent | archived
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # pending | no_reply | replied_positive | replied_neutral | replied_negative | meeting | won
    outcome: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    company: Mapped[Company] = relationship(back_populates="messages")
    contact: Mapped[Optional[Contact]] = relationship()


class OutreachEvent(TimestampMixin, Base):
    __tablename__ = "outreach_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("outreach_messages.id", ondelete="SET NULL"))
    # connection_requested | connected | message_sent | follow_up_sent | replied | meeting | not_interested |
    # won | lost | note | do_not_contact
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="linkedin", nullable=False)
    strategy: Mapped[Optional[str]] = mapped_column(String(2))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="events")


class FollowUpTask(TimestampMixin, Base):
    __tablename__ = "follow_up_tasks"
    __table_args__ = (Index("ix_tasks_status_due", "status", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    task_type: Mapped[str] = mapped_column(String(32), default="follow_up", nullable=False)  # follow_up | check_connection | call | custom
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | done | cancelled
    sequence_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancelled_reason: Mapped[Optional[str]] = mapped_column(String(200))

    company: Mapped[Company] = relationship(back_populates="tasks")
    contact: Mapped[Optional[Contact]] = relationship()


class SuppressionEntry(TimestampMixin, Base):
    """Do Not Contact – firmy a osoby, které nesmí být znovu oslovovány."""

    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(253), index=True)
    ico: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(64), nullable=False)  # refused | requested_removal | manual | competitor
    note: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Automatizace
# ---------------------------------------------------------------------------
class AutomationJob(TimestampMixin, Base):
    __tablename__ = "automation_jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_after", "status", "run_after"),
        Index("ix_jobs_dedupe", "dedupe_key", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)  # queued|running|done|failed|cancelled
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # nižší = dřív
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(200))
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)  # manual | scheduler | system
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("automation_jobs.id", ondelete="SET NULL"))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    worker: Mapped[Optional[str]] = mapped_column(String(64))
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    log: Mapped[list] = mapped_column(JSON, default=list)


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
