from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.main import app


def test_healthz_always_ok():
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz_not_ready_without_key(monkeypatch):
    # force a keyless Settings (init kwarg wins over .env and os.environ)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(anthropic_api_key=None))
    r = TestClient(app).get("/readyz")
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["missing"]


def test_readyz_ready_with_key(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(anthropic_api_key="sk-test-dummy"))
    r = TestClient(app).get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
