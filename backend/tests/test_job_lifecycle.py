"""
Integration tests for the Job lifecycle (Task 5 skeleton + Task 15 real loop).

These drive the *real* Orchestrator loop (`agent.step` + `classify_step`) and
the real Job Manager dispatch loop, with a `FakeModelClient` injected via
`manager.set_test_dependencies(...)` so the model turn is deterministic and no
Ollama is required. The pre–Task-15 version of these tests asserted the stub
Orchestrator's `"Echo: ..."` output; that stub is gone.
"""

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

# Repo root on path so `backend.*` / `scripts.*` resolve when pytest is invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.main import app
from backend.config import settings
from backend.domain.audit.events import get_events_for_job
from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.job_manager import manager
from backend.models.schemas import GenerationResult
from backend.repositories import (
    artifacts as artifacts_repo,
    conversations as conversations_repo,
    jobs as jobs_repo,
)
from backend.repositories.db import get_connection
import scripts.init_db as init_db


CAPABILITIES_CONFIG = {
    "capabilities": {
        "extract_document": {"enabled": True, "timeout_seconds": 120, "max_file_size_mb": 10},
        "search_knowledge_base": {"enabled": True, "timeout_seconds": 10, "default_top_k": 5},
        "generate_code": {"enabled": True, "timeout_seconds": 30},
        "execute_code": {"enabled": True, "timeout_seconds": 30, "cpu_limit": 1, "memory_limit_mb": 512, "max_output_bytes": 65536},
        "create_docx": {"enabled": True, "timeout_seconds": 15},
        "create_xlsx": {"enabled": True, "timeout_seconds": 15},
    }
}

ANSWER = "The maintenance window is 02:00–04:00 UTC on the first Sunday."


class FakeModelClient:
    """Returns scripted raw model outputs, one per `generate` call."""

    def __init__(self, responses: List[str]):
        self._responses = responses
        self._i = 0
        self.calls: List[Dict[str, Any]] = []

    async def generate(
        self,
        resource_type: str,
        prompt: str,
        *,
        images: Optional[List[bytes]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        self.calls.append({"resource_type": resource_type, "prompt": prompt})
        text = self._responses[self._i] if self._i < len(self._responses) else "{}"
        self._i += 1
        return GenerationResult(text=text, prompt_tokens=10, completion_tokens=5, duration_ms=1)


def create_temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    original = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original
    return db_path


@pytest.fixture
def temp_db():
    db_path = create_temp_db()
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client(temp_db):
    import backend.repositories.db as db_module
    import backend.repositories.audit_events as audit_events_repo

    originals = {
        "jobs": jobs_repo.get_connection,
        "conv": conversations_repo.get_connection,
        "artifacts": artifacts_repo.get_connection,
        "db": db_module.get_connection,
        "audit": audit_events_repo.get_connection,
    }
    patched = lambda: get_connection(temp_db)
    jobs_repo.get_connection = patched
    conversations_repo.get_connection = patched
    artifacts_repo.get_connection = patched
    db_module.get_connection = patched
    audit_events_repo.get_connection = patched

    # Deterministic Orchestrator: a single direct answer, no capability.
    manager.set_test_dependencies(
        model_client=FakeModelClient([json.dumps({"action": "respond", "content": ANSWER})]),
        registry=CapabilityRegistry(CAPABILITIES_CONFIG),
        capabilities_config=CAPABILITIES_CONFIG,
    )

    with TestClient(app) as test_client:
        yield test_client

    manager.reset_test_dependencies()
    jobs_repo.get_connection = originals["jobs"]
    conversations_repo.get_connection = originals["conv"]
    artifacts_repo.get_connection = originals["artifacts"]
    db_module.get_connection = originals["db"]
    audit_events_repo.get_connection = originals["audit"]


def _wait_terminal(job_id: str, timeout: float = 10.0) -> dict:
    waited = 0.0
    while waited < timeout:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
        waited += 0.05
    return jobs_repo.get_job(job_id)


def _create_job(client, conv_id: str, message: str = "When is the maintenance window?") -> str:
    resp = client.post(
        "/api/v1/jobs",
        json={"conversation_id": conv_id, "message": message, "document_ids": []},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


def test_create_job_returns_201_and_creates_row(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    resp = client.post(
        "/api/v1/jobs",
        json={"conversation_id": conv_id, "message": "Test message", "document_ids": []},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert "job_id" in data and "created_at" in data

    job = jobs_repo.get_job(data["job_id"])
    assert job is not None
    assert job["input_message"] == "Test message"
    assert job["conversation_id"] == conv_id

    events = asyncio.run(get_events_for_job(data["job_id"]))
    created = [e for e in events if e["event_type"] == "job_created"]
    assert len(created) == 1
    assert created[0]["payload"]["input_message"] == "Test message"


def test_create_job_with_document_ids_enriches_user_message(client, temp_db):
    """document_ids reach the Orchestrator via an attachment note in the stored
    user message (Workflow A fix: the Orchestrator needs the document_id to
    propose extract_document — docs/demo.md step 1). The Job row and the
    job_created event keep the raw input_message."""
    conv_id = conversations_repo.create_conversation()
    resp = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Review the attached report and draft an approval note.",
            "document_ids": ["doc-uuid-1", "doc-uuid-2"],
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    _wait_terminal(job_id)

    # Job row keeps the raw message
    job = jobs_repo.get_job(job_id)
    assert job["input_message"] == "Review the attached report and draft an approval note."

    # job_created event keeps the raw message
    events = asyncio.run(get_events_for_job(job_id))
    created = [e for e in events if e["event_type"] == "job_created"]
    assert created[0]["payload"]["input_message"] == "Review the attached report and draft an approval note."

    # Conversation history carries the attachment note with every id
    user_messages = [m for m in conversations_repo.list_messages(conv_id) if m["role"] == "user"]
    assert len(user_messages) == 1
    content = user_messages[0]["content"]
    assert content.startswith("Review the attached report and draft an approval note.")
    assert "document_id=doc-uuid-1" in content
    assert "document_id=doc-uuid-2" in content


def test_create_job_without_document_ids_keeps_message_unmodified(client, temp_db):
    """No document_ids → stored user message is exactly the input message
    (no attachment note)."""
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id, message="plain question")
    _wait_terminal(job_id)

    user_messages = [m for m in conversations_repo.list_messages(conv_id) if m["role"] == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "plain question"


def test_job_completes_with_final_message(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id)

    job = _wait_terminal(job_id)
    assert job["status"] == "completed"
    assert job["final_message"] == ANSWER
    assert job["error_code"] is None

    data = client.get(f"/api/v1/jobs/{job_id}").json()
    assert data["status"] == "completed"
    assert data["final_message"] == ANSWER
    assert data["artifact_ids"] == []
    assert data["error"] is None


def test_job_step_created_orchestrator_reasoning(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id)
    _wait_terminal(job_id)

    steps = jobs_repo.list_job_steps(job_id)
    assert len(steps) == 1
    assert steps[0]["kind"] == "orchestrator_reasoning"
    assert steps[0]["status"] == "succeeded"
    assert steps[0]["capability_name"] is None
    assert jobs_repo.list_capability_executions_by_job_step(steps[0]["job_step_id"]) == []


def test_orchestrator_message_row_created(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id)
    _wait_terminal(job_id)

    messages = conversations_repo.list_messages(conv_id)
    roles = [m["role"] for m in messages]
    assert roles == ["user", "orchestrator"]
    orch = [m for m in messages if m["role"] == "orchestrator"][0]
    assert orch["job_id"] == job_id
    assert orch["content"] == ANSWER


def test_trace_returns_ordered_events(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id)
    _wait_terminal(job_id)

    data = client.get(f"/api/v1/jobs/{job_id}/trace").json()
    assert data["job_id"] == job_id
    types = [e["event_type"] for e in data["events"]]
    assert "job_created" in types
    assert "orchestrator_step" in types
    assert "job_completed" in types
    timestamps = [e["timestamp"] for e in data["events"]]
    assert timestamps == sorted(timestamps)


def test_sse_streams_and_closes_on_job_completed(client, temp_db):
    conv_id = conversations_repo.create_conversation()
    job_id = _create_job(client, conv_id)
    _wait_terminal(job_id)

    with client.stream("GET", f"/api/v1/jobs/{job_id}/events?replay=true") as sse:
        assert sse.status_code == 200
        received = []
        for line in sse.iter_lines():
            if line.startswith("data: "):
                received.append(json.loads(line[6:]))
                if received[-1]["event_type"] == "job_completed":
                    break
    types = [e["event_type"] for e in received]
    assert "job_created" in types
    assert "job_completed" in types


def test_unknown_job_returns_404(client, temp_db):
    unknown = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/jobs/{unknown}")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "not_found"
    assert client.get(f"/api/v1/jobs/{unknown}/trace").status_code == 404
    assert client.get(f"/api/v1/jobs/{unknown}/events").status_code == 404


def test_invalid_conversation_returns_404(client, temp_db):
    r = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": "00000000-0000-0000-0000-000000000000",
            "message": "Test message",
            "document_ids": [],
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "not_found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
