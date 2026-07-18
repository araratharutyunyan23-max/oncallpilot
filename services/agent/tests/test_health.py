from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_healthz_always_ok():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz_not_ready_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    c = TestClient(app)
    r = c.get("/readyz")
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["missing"]
    get_settings.cache_clear()


def test_readyz_ready_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-dummy")
    get_settings.cache_clear()
    c = TestClient(app)
    r = c.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    get_settings.cache_clear()
