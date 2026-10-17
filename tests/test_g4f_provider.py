"""Tests for G4FProvider — mocks g4f so no network calls are made."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app


def _make_g4f_response(content: str):
    """Build a minimal fake g4f response object."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_g4f_models_listed():
    """g4f:auto and friends should appear in /v1/models."""
    with TestClient(app) as client:
        response = client.get("/v1/models")
    assert response.status_code == 200
    ids = {m["id"] for m in response.json()["data"]}
    assert "g4f:auto" in ids
    assert "g4f:gpt-4o" in ids


def test_g4f_chat_completion(monkeypatch):
    """POST /v1/chat/completions with model=g4f:auto returns valid OpenAI shape."""
    fake_resp = _make_g4f_response("Hello from g4f!")

    async def fake_create(**kwargs):
        return fake_resp

    with patch("app.providers.g4f_provider.G4FProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello from g4f!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6},
        }
        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json={
                "model": "g4f:auto",
                "messages": [{"role": "user", "content": "hello"}],
            })

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "Hello from g4f!"
    assert body["system_fingerprint"]
    assert body["usage"]["total_tokens"] == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]


def test_g4f_health_check():
    with TestClient(app) as client:
        response = client.get("/health/providers")
    assert response.status_code == 200
    data = response.json()
    assert "g4f" in data
    assert "deepbridge" in data
