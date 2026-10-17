"""Integration-level rate limiting tests (via HTTP)."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.ratelimit import reset_rate_limits


def test_rate_limit_returns_429_after_capacity_exceeded(monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.get_settings", lambda: type("S", (), {
        "rate_limit_enabled": True,
        "rate_limit_requests": 2,
        "rate_limit_window_seconds": 60.0,
    })())
    reset_rate_limits()

    with TestClient(app) as client:
        r1 = client.get("/v1/models")
        r2 = client.get("/v1/models")
        r3 = client.get("/v1/models")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert r3.json()["error"]["code"] == "rate_limit_exceeded"


def test_rate_limit_disabled_allows_all(monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.get_settings", lambda: type("S", (), {
        "rate_limit_enabled": False,
        "rate_limit_requests": 1,
        "rate_limit_window_seconds": 60.0,
    })())
    reset_rate_limits()

    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/v1/models").status_code == 200
