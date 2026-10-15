from fastapi.testclient import TestClient
from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["author"] == "@flexOwnerAL"


def test_models_include_deepbridge_models():
    with TestClient(app) as client:
        response = client.get("/v1/models")

    assert response.status_code == 200

    data = response.json()["data"]
    model_ids = {model["id"] for model in data}

    assert "deepseek-chat" in model_ids
    assert "deepseek-expert" in model_ids
