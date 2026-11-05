def test_meta_and_dashboard(app_client):
    m = app_client.get("/api/meta").json()
    assert len(m["segments"]) >= 30 and len(m["strategies"]) == 5
    assert app_client.get("/api/dashboard").status_code == 200


def test_company_lifecycle(app_client):
    r = app_client.post("/api/companies", json={"name": "API Test Studio", "website": "https://api-test-studio.cz",
                                                "city": "Praha", "segment_key": "pilates_studio", "analyze": False})
    assert r.status_code == 200
    cid = r.json()["company_id"]
    d = app_client.get(f"/api/companies/{cid}").json()
    assert d["segment_label"] == "Pilates studia"
    assert any("linkedin.com" in link["url"] for link in d["linkedin"]["links"])
    r = app_client.post(f"/api/companies/{cid}/contacts", json={"name": "Eva Krátká", "role": "Founder",
                                                               "linkedin_url": "linkedin.com/in/eva-kratka"})
    assert r.json()["linkedin_url"] == "https://www.linkedin.com/in/eva-kratka"
    r = app_client.post(f"/api/companies/{cid}/messages/generate", json={"strategy": "E", "use_llm": False})
    msgs = r.json()["messages"]
    assert len(msgs) == 5 and all(m["strategy"] == "E" for m in msgs)
    first = next(m for m in msgs if m["message_type"] == "first_message")
    r = app_client.post(f"/api/companies/{cid}/outreach/contacted", json={"message_id": first["id"], "kind": "message_sent"})
    assert r.status_code == 200 and r.json()["task_id"]
    tasks = app_client.get("/api/tasks?scope=open").json()
    assert any(t["company_id"] == cid for t in tasks)
    r = app_client.post(f"/api/companies/{cid}/outreach/not-interested", json={"explicit_refusal": True})
    assert r.json()["suppressed"] is True
    assert app_client.post(f"/api/companies/{cid}/messages/generate", json={"strategy": "A"}).status_code == 409
    assert any(s["domain"] == "api-test-studio.cz" for s in app_client.get("/api/suppression").json())


def test_settings_validation(app_client):
    s = app_client.get("/api/settings").json()
    bad = s["scoring"]
    bad["weights"]["design_gap"] = 0.9
    assert app_client.put("/api/settings/scoring", json=bad).status_code == 400
    auto = s["automation"]
    auto["daily_discovery_target"] = 50
    assert app_client.put("/api/settings/automation", json=auto).json()["daily_discovery_target"] == 50


def test_pause_resume(app_client):
    assert app_client.post("/api/automation/pause").json()["paused"] is True
    assert app_client.get("/api/automation").json()["paused"] is True
    assert app_client.post("/api/automation/resume").json()["paused"] is False


def test_screenshot_path_traversal(app_client):
    assert app_client.get("/screenshots/../../etc/passwd").status_code == 404
