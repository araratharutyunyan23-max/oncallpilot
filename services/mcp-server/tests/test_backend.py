from app.backends import MockBackend


def test_ci_status_latest_is_failed():
    r = MockBackend().ci_status("api-deploy", None, 10)
    assert r["pipeline"] == "api-deploy"
    assert r["count"] >= 1
    assert r["runs"][0]["status"] == "failed"  # seeded scenario: api-deploy is red


def test_ci_status_branch_filter():
    r = MockBackend().ci_status("api-deploy", "does-not-exist", 10)
    assert r["count"] == 0


def test_alerts_firing_only():
    r = MockBackend().alerts("firing", None, None, 20)
    assert r["alerts"]
    assert all(a["state"] == "firing" for a in r["alerts"])
    assert any(a["labels"] == ["HighApiErrorRate"] for a in r["alerts"])


def test_alerts_severity_filter():
    r = MockBackend().alerts("firing", None, "P1", 20)
    assert all(a["severity"] == "P1" for a in r["alerts"])


def test_create_ticket_idempotent():
    b = MockBackend()
    t1 = b.create_ticket("SRE", "s", "d", "Incident", "P1", ["x"], "idem-1")
    assert t1["status"] == "created"
    t2 = b.create_ticket("SRE", "s", "d", "Incident", "P1", ["x"], "idem-1")
    assert t2["status"] == "deduped"
    assert t2["ticket_key"] == t1["ticket_key"]  # no second ticket
    t3 = b.create_ticket("SRE", "s2", "d2", "Incident", "P2", [], "idem-2")
    assert t3["status"] == "created"
    assert t3["ticket_key"] != t1["ticket_key"]
