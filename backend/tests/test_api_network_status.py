"""docs/api.md contract tests for GET /api/v1/network-status + the monitor (Task 15 Req 4)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.domain.monitoring import network_monitor
from backend.main import app
from backend.repositories.audit_events import query_by_event_type


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_network_status_shape(client):
    r = client.get("/api/v1/network-status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"external_connections_detected", "checked_at", "monitoring_since"}
    assert body["external_connections_detected"] is False
    assert isinstance(body["checked_at"], str) and body["checked_at"]
    assert isinstance(body["monitoring_since"], str) and body["monitoring_since"]


def test_monitor_running_after_startup(client):
    assert network_monitor.get_status()["checked_at"] is not None


def test_check_once_emits_network_check_event(isolated_db):
    """A poll writes a `network_check` audit event with job_id null (docs/audit.md)."""
    asyncio.run(network_monitor._check_once())

    rows = query_by_event_type("network_check", limit=10)
    assert rows, "expected a network_check event"
    assert rows[0]["job_id"] is None
    payload = json.loads(rows[0]["payload"])
    assert set(payload) >= {"external_connections_detected", "checked_at"}
    assert payload["external_connections_detected"] is False


def test_is_external_classifier():
    assert network_monitor._is_external("8.8.8.8") is True
    assert network_monitor._is_external("127.0.0.1") is False
    assert network_monitor._is_external("::1") is False
    assert network_monitor._is_external("0.0.0.0") is False
    assert network_monitor._is_external(None) is False
    assert network_monitor._is_external("not-an-ip") is False
