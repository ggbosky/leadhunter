from datetime import timedelta

from sqlalchemy import select

from app.connectors.base import RawCompany
from app.connectors.registry import ensure_data_sources
from app.jobs.queue import JobDeferred, claim_next, enqueue, handler, run_job
from app.models import AutomationJob, Company, Contact, FollowUpTask, SuppressionEntry, utcnow
from app.services.dedup import upsert_company
from app.services.messages import compose_fallback, gather_facts, quality_check
from app.services.outreach import mark_contacted, mark_not_interested, record_reply, schedule_follow_up


def _raw(**kw):
    base = dict(source_key="osm", external_id="node/1", name="Květiny Jana", city="Brno", website="https://kvetiny-jana.cz",
                segment_key="premium_florist")
    base.update(kw)
    return RawCompany(**base)


def test_dedup_updates_existing(db):
    ds = ensure_data_sources(db)
    c1, created1, _ = upsert_company(db, _raw(external_id="node/100", website="https://dedup-a.cz", name="Dedup A"), ds["osm"])
    c2, created2, match = upsert_company(db, _raw(source_key="brave", external_id="dedup-a.cz", website="http://www.dedup-a.cz/kontakt",
                                                  name="Dedup A – květiny", phone="777 111 222"), ds["brave"])
    assert created1 and not created2 and c1.id == c2.id and match == "domain"
    assert c2.phone == "+420777111222" and c2.times_seen == 2
    # stejný název + město bez webu
    c3, created3, match3 = upsert_company(db, _raw(external_id="node/101", website=None, name="Dedup A, s.r.o.", city="Brno"), ds["osm"])
    assert not created3 and match3 == "name_city"
    # stejné město, podobný název, ale bez ulice → NESMÍ se sloučit
    c5, created5, _ = upsert_company(db, _raw(external_id="node/103", website=None, name="Dedup B", city="Brno"), ds["osm"])
    assert created5 and c5.id != c1.id
    # stejná adresa s ulicí + velmi podobný název → sloučit
    c6, _, _ = upsert_company(db, _raw(external_id="node/104", website=None, name="Atelier Lumen", street="Údolní 12", city="Brno"), ds["osm"])
    c7, created7, match7 = upsert_company(db, _raw(external_id="node/105", website=None, name="Ateliér Lumen", street="Údolní 12", city="Brno ", postcode=None), ds["osm"])
    assert not created7 and c7.id == c6.id
    # sociální síť není web
    c4, _, _ = upsert_company(db, _raw(external_id="node/102", website="https://facebook.com/studio-b", name="Studio B"), ds["osm"])
    assert c4.website_url is None and "facebook" in c4.social_links
    db.commit()


def _company(db, name="Workflow s.r.o.", domain="workflow-test.cz"):
    ds = ensure_data_sources(db)
    c, _, _ = upsert_company(db, _raw(external_id=f"node/{domain}", website=f"https://{domain}", name=name), ds["osm"])
    ct = Contact(company_id=c.id, name="Petra Malá", role="Majitelka", linkedin_url=f"https://www.linkedin.com/in/pm-{domain}", is_decision_maker=True)
    db.add(ct)
    c.contacts.append(ct)
    db.flush()
    return c, ct


def test_outreach_reply_stops_followups(db):
    c, ct = _company(db, "Reply Test", "reply-test.cz")
    mark_contacted(db, c, contact=ct, kind="message_sent")
    open_tasks = db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == c.id, FollowUpTask.status == "open")).all()
    assert len(open_tasks) == 1 and c.status == "contacted"
    record_reply(db, c, outcome="replied_neutral", contact=ct)
    open_tasks = db.scalars(select(FollowUpTask).where(FollowUpTask.company_id == c.id, FollowUpTask.status == "open")).all()
    assert open_tasks == [] and c.status == "replied"
    db.commit()


def test_refusal_adds_to_dnc(db):
    c, ct = _company(db, "Refusal Test", "refusal-test.cz")
    mark_contacted(db, c, contact=ct)
    mark_not_interested(db, c, contact=ct, explicit_refusal=True, notes="Nemám zájem")
    assert c.status == "disqualified" and c.disqualified_reason == "do_not_contact"
    assert db.scalar(select(SuppressionEntry).where(SuppressionEntry.domain == "refusal-test.cz")) is not None
    assert ct.do_not_contact
    import pytest

    from app.services.outreach import OutreachBlocked

    with pytest.raises(OutreachBlocked):
        mark_contacted(db, c, contact=ct)
    db.commit()


def test_followup_limit(db):
    c, ct = _company(db, "Limit Test", "limit-test.cz")
    tasks = [schedule_follow_up(db, c, contact=ct) for _ in range(5)]
    assert tasks[-1] is None  # max_followups=2 (+ první) → další už se neplánují
    db.commit()


def test_message_composer_and_quality(db):
    c, ct = _company(db, "Message Test", "message-test.cz")
    facts = gather_facts(db, c, ct)
    agency = {"portfolio": [], "facts": []}
    for strategy in "ABCDE":
        texts = compose_fallback(c, ct, facts, strategy, "Karel", agency)
        assert set(texts) == {"connection_request", "first_message", "follow_up", "alternative", "pitch"}
        assert len(texts["connection_request"]) <= 280
        assert "špatný web" not in texts["first_message"].lower()
    warnings = quality_check("first_message", "Máte špatný web, zvýšíme tržby o 50 %!!", {"connection_request": 280, "first_message": 900}, facts)
    assert any("nevhodnou frázi" in w for w in warnings)
    assert any("číselný slib" in w for w in warnings)


@handler("test_flaky")
def _flaky(db, job):
    if job.attempts < 2:
        raise RuntimeError("dočasná chyba")
    return {"ok": True}


@handler("test_defer")
def _defer(db, job):
    raise JobDeferred(300, "čekám")


def test_queue_retry_and_dedupe(db):
    j = enqueue(db, "test_flaky", {}, dedupe_key="flaky-1")
    j2 = enqueue(db, "test_flaky", {}, dedupe_key="flaky-1")
    assert j.id == j2.id
    db.commit()
    claimed = claim_next(db, "t")
    assert claimed.id == j.id
    run_job(j.id)
    db.expire_all()
    job = db.get(AutomationJob, j.id)
    assert job.status == "queued" and job.attempts == 1 and job.run_after > utcnow()
    job.run_after = utcnow() - timedelta(seconds=1)
    db.commit()
    claim_next(db, "t")
    run_job(j.id)
    db.expire_all()
    assert db.get(AutomationJob, j.id).status == "done"


def test_queue_defer_does_not_consume_attempt(db):
    j = enqueue(db, "test_defer", {})
    db.commit()
    claim_next(db, "t")
    run_job(j.id)
    db.expire_all()
    job = db.get(AutomationJob, j.id)
    assert job.status == "queued" and job.attempts == 0
    job.status = "cancelled"
    db.commit()


def test_refused_person_blocked_across_companies(db):
    """Odmítnutí osoby (LinkedIn URL) blokuje oslovení i přes jinou firmu."""
    import pytest

    from app.services.outreach import OutreachBlocked

    c1, ct1 = _company(db, "Person A", "person-a.cz")
    mark_not_interested(db, c1, contact=ct1, explicit_refusal=True)
    ds = ensure_data_sources(db)
    c2, _, _ = upsert_company(db, _raw(external_id="node/person-b", website="https://person-b.cz", name="Person B"), ds["osm"])
    ct2 = Contact(company_id=c2.id, name=ct1.name, linkedin_url=ct1.linkedin_url)
    db.add(ct2)
    db.flush()
    with pytest.raises(OutreachBlocked):
        mark_contacted(db, c2, contact=ct2)
    db.rollback()
