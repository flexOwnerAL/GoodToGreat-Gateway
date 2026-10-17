from fastapi.testclient import TestClient
from app.main import app


def test_retrieve_known_model():
    with TestClient(app) as client:
        response = client.get("/v1/models/deepseek-chat")
    assert response.status_code == 200
    assert response.json()["id"] == "deepseek-chat"


def test_retrieve_unknown_model_returns_404():
    with TestClient(app) as client:
        response = client.get("/v1/models/not-a-real-model-xyz")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "model_not_found"
    assert error["param"] == "model"


def test_error_envelope_has_required_keys():
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 400
    error = response.json()["error"]
    assert {"message", "type", "param", "code"} <= set(error.keys())


def test_n_greater_than_one_is_rejected():
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json={
            "model": "g4f:auto",
            "messages": [{"role": "user", "content": "hi"}],
            "n": 2,
        })
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "n"


def test_oversized_body_rejected(monkeypatch):
    monkeypatch.setattr("app.main.settings.max_request_body_bytes", 10)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "g4f:auto", "messages": [{"role": "user", "content": "x" * 200}]},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_api_key_protects_v1_routes(monkeypatch):
    monkeypatch.setattr("app.main.settings.gtg_api_key", "test-secret-key")
    with TestClient(app) as client:
        denied = client.get("/v1/models")
        allowed = client.get("/v1/models", headers={"Authorization": "Bearer test-secret-key"})
    assert denied.status_code == 401
    assert allowed.status_code == 200
