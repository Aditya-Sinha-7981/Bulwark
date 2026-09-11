"""docs/api.md contract tests for GET /api/v1/health (Task 15 Req 3).

Probes are monkeypatched so the test does not depend on a live Ollama / Docker.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api import health as health_module
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _set_probes(monkeypatch, *, db=True, ollama=True, docker=True):
    monkeypatch.setattr(health_module, "_probe_database", lambda: db)
    monkeypatch.setattr(health_module, "_probe_ollama", lambda: ollama)
    monkeypatch.setattr(health_module, "_probe_docker", lambda: docker)


def test_health_all_ok(client, monkeypatch):
    _set_probes(monkeypatch)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "backend": "ok",
        "database": "ok",
        "model_runtime": "ok",
        "docker": "ok",
    }


def test_health_reports_ollama_and_docker_unavailable(client, monkeypatch):
    _set_probes(monkeypatch, ollama=False, docker=False)
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"          # health never 503s / degrades `status`
    assert body["backend"] == "ok"
    assert body["database"] == "ok"
    assert body["model_runtime"] == "unavailable"
    assert body["docker"] == "unavailable"


def test_health_reports_database_unavailable(client, monkeypatch):
    _set_probes(monkeypatch, db=False)
    body = client.get("/api/v1/health").json()
    assert body["database"] == "unavailable"
    assert body["status"] == "ok"


def test_health_values_are_within_documented_enum(client, monkeypatch):
    _set_probes(monkeypatch)
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["backend"] == "ok"
    assert body["database"] in {"ok", "unavailable"}
    assert body["model_runtime"] in {"ok", "unavailable"}
    assert body["docker"] in {"ok", "unavailable"}
