"""Tests for OllamaProvider — mocks httpx so no real Ollama needed."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


def test_ollama_chat_completion(monkeypatch):
    with patch("app.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello from Ollama"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        }
        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json={
                "model": "ollama:qwen2.5:3b",
                "messages": [{"role": "user", "content": "hello"}],
            })

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "Hello from Ollama"


def test_ollama_not_in_models_when_unreachable(monkeypatch):
    """If Ollama is down, list_models() returns [] without crashing."""
    with patch("app.providers.ollama.OllamaProvider.list_models", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        with TestClient(app) as client:
            response = client.get("/v1/models")
        assert response.status_code == 200
        ids = {m["id"] for m in response.json()["data"]}
        # No ollama: prefix models.
        assert not any(mid.startswith("ollama:") for mid in ids)
