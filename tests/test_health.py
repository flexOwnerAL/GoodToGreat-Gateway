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
    data = response.json()
    assert data["author"] == "@flexOwnerAL"
    assert "deepbridge" in data["providers"]


def test_models_include_deepbridge():
    with TestClient(app) as client:
        response = client.get("/v1/models")
    assert response.status_code == 200
    ids = {m["id"] for m in response.json()["data"]}
    assert "deepseek-chat" in ids
    assert "deepseek-expert" in ids
