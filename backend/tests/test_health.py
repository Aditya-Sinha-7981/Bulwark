from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

ALLOWED = {
    "status": {"ok"},
    "backend": {"ok"},
    "database": {"ok", "unavailable"},
    "model_runtime": {"ok", "unavailable"},
    "docker": {"ok", "unavailable"},
}


def test_health_returns_200():
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_shape_and_values():
    body = client.get("/api/v1/health").json()
    assert set(body.keys()) == set(ALLOWED.keys())
    assert body["status"] == "ok"
    assert body["backend"] == "ok"
    for field, allowed_values in ALLOWED.items():
        assert body[field] in allowed_values
