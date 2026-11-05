from app.scoring.engine import LeadContext, category_for, score_lead

RICH_EXTRACTED = {
    "pages_crawled": ["home", "portfolio", "services", "contact"],
    "portfolio_image_count": 34,
    "socials": {"instagram": "x", "facebook": "y", "pinterest": "z"},
    "quality": {"testimonials": 4, "awards": 1, "press": 0, "premium": 5, "weddings": 6, "b2b": 0, "team": 1, "branches": 1},
    "total_word_count": 1800,
    "price_count": 6,
    "price_median": 8000,
    "technologies": ["Meta Pixel"],
    "since_year": 2009,
}


def ctx(**kw):
    base = dict(company_name="Test", segment_key="premium_florist", has_website=True, website_reachable=True,
                extracted=RICH_EXTRACTED, technical_score=40)
    base.update(kw)
    return LeadContext(**base)


def test_categories():
    assert category_for(85) == "priority"
    assert category_for(60) == "strong"
    assert category_for(40) == "potential"
    assert category_for(10) == "low"
    assert category_for(None) == "insufficient"


def test_unknown_is_not_zero():
    """Firma bez analyzovaného webu nesmí dostat nulové Design Gap ani Opportunity."""
    res = score_lead(LeadContext(company_name="X", segment_key="interior_design", has_website=True))
    assert res["design_gap"] is None
    assert res["buying_readiness"] is None
    assert res["opportunity_score"] is None
    assert res["category"] == "insufficient"
    assert any(d["code"] == "insufficient_data" for d in res["disqualification_reasons"])


def test_visual_gap_ideal_lead():
    visual = {"status": "complete", "visual_score": 25, "confidence": 0.8, "business_quality_score": 85,
              "criteria": [{"key": "photography", "score": 80}, {"key": "brand_consistency", "score": 50}]}
    res = score_lead(ctx(visual=visual, signals=[{"signal_type": "new_branch", "strength": 0.75, "age_factor": 1.0,
                                                  "description": "Nová pobočka", "evidence": "otevíráme"}],
                         contacts=[{"name": "Jana Nová", "role": "Majitelka", "linkedin_url": "https://www.linkedin.com/in/jn"}]))
    assert res["website_quality_basis"] == "visual"
    assert res["design_gap"] > 60
    assert res["opportunity_score"] >= 60
    assert res["category"] in ("strong", "priority")
    assert res["estimated_budget"]["min"] > 0


def test_good_website_is_disqualified():
    visual = {"status": "complete", "visual_score": 88, "confidence": 0.8, "business_quality_score": 80, "criteria": []}
    res = score_lead(ctx(visual=visual, technical_score=95))
    assert any(d["code"] == "good_website" for d in res["disqualification_reasons"])
    assert res["design_gap"] < 30


def test_technical_only_has_lower_confidence():
    visual = {"status": "complete", "visual_score": 30, "confidence": 0.8, "business_quality_score": 80, "criteria": []}
    a = score_lead(ctx(visual=visual))
    b = score_lead(ctx(visual={"status": "incomplete"}, technical_score=30))
    assert b["website_quality_basis"] == "technical"
    assert b["components"]["design_gap"]["confidence"] < a["components"]["design_gap"]["confidence"]


def test_suppressed_flag():
    res = score_lead(ctx(suppressed=True))
    assert any(d["code"] == "do_not_contact" for d in res["disqualification_reasons"])


def test_weights_sum_and_component_reasons():
    res = score_lead(ctx(visual={"status": "complete", "visual_score": 40, "confidence": 0.7, "criteria": []}))
    comps = res["components"]
    for k in ("design_gap", "commercial_potential", "buying_readiness", "service_fit", "contactability"):
        assert "reasons" in comps[k]
    assert abs(sum(comps["weights"].values()) - 1.0) < 1e-6
