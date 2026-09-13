"""
End-to-end workflow tests (Task 15 §8).

Two tiers:

* Non-integration: a real request travels HTTP → Job Manager → real Orchestrator
  loop → Policy → the single dispatch seam → executor → trace, with only the
  *model turn* faked (deterministic, no Ollama). This proves the wiring and the
  no-bypass path for the `respond` and real `create_docx` workflows, and that
  `/trace` is exactly a filtered `audit_events` query.

* Integration (`@pytest.mark.integration`, skipped unless Ollama + a seeded KB
  are present): the real Workflow C (`docs/demo.md`) — `search_knowledge_base`
  proposed by the real model, Policy `allow`, retrieval executor, grounded
  answer. This lights up once Tasks 12.a/12.b merge; the retrieval executor is
  still a stub today.
"""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.job_manager import manager
from backend.models.schemas import GenerationResult
from backend.repositories.audit_events import query_by_job_id
from backend.utils import paths as paths_module

CAPS = {
    "capabilities": {
        "extract_document": {"enabled": True, "timeout_seconds": 120, "max_file_size_mb": 10},
        "search_knowledge_base": {"enabled": True, "timeout_seconds": 10, "default_top_k": 5},
        "generate_code": {"enabled": True, "timeout_seconds": 30},
        "execute_code": {"enabled": True, "timeout_seconds": 30, "cpu_limit": 1, "memory_limit_mb": 512, "max_output_bytes": 65536},
        "create_docx": {"enabled": True, "timeout_seconds": 15},
        "create_xlsx": {"enabled": True, "timeout_seconds": 15},
    }
}
POLICY = {"policy": {"network_access_allowed": False, "max_job_steps": 8, "malformed_output_free_retries": 1}}

DOCX_ARGS = {
    "title": "Approval Note",
    "sections": [{"heading": "Decision", "body": "Approved."}],
    "metadata": {"prepared_by": "Reviewer", "date": "2026-09-10"},
}


class ScriptedModel:
    def __init__(self, responses):
        self._responses = responses
        self._i = 0

    async def generate(self, resource_type, prompt, *, images=None, options=None):
        text = self._responses[self._i] if self._i < len(self._responses) else json.dumps(
            {"action": "respond", "content": "done"}
        )
        self._i += 1
        return GenerationResult(text=text, prompt_tokens=1, completion_tokens=1, duration_ms=1)


@pytest.fixture
def client(isolated_db, monkeypatch, tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setattr(paths_module, "ARTIFACTS_ROOT", root)
    monkeypatch.setattr(paths_module, "artifacts_path", lambda aid, ext: root / f"{aid}{ext}")
    # api/artifacts.py bound ARTIFACTS_ROOT at import time — rebind that name too.
    import backend.api.artifacts as artifacts_api

    monkeypatch.setattr(artifacts_api, "ARTIFACTS_ROOT", root)
    with TestClient(app_ref()) as c:
        c.artifacts_root = root  # type: ignore[attr-defined]
        yield c
    manager.reset_test_dependencies()


def app_ref():
    from backend.main import app

    return app


def _install(responses):
    manager.set_test_dependencies(
        model_client=ScriptedModel(responses),
        registry=CapabilityRegistry(CAPS),
        capabilities_config=CAPS,
        policy_config=POLICY,
    )


def _poll(client, job_id, timeout=10.0):
    waited = 0.0
    while waited < timeout:
        body = client.get(f"/api/v1/jobs/{job_id}").json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
        waited += 0.05
    return client.get(f"/api/v1/jobs/{job_id}").json()


def _run_job(client, message):
    conv_id = client.post("/api/v1/conversations").json()["conversation_id"]
    job = client.post(
        "/api/v1/jobs",
        json={"conversation_id": conv_id, "message": message, "document_ids": []},
    ).json()
    return conv_id, job["job_id"]


# --------------------------------------------------------------------------- #
# Non-integration: full HTTP path, model turn faked
# --------------------------------------------------------------------------- #

def test_e2e_direct_answer_over_http(client):
    _install([json.dumps({"action": "respond", "content": "42"})])
    _conv, job_id = _run_job(client, "what is the answer")

    body = _poll(client, job_id)
    assert body["status"] == "completed"
    assert body["final_message"] == "42"
    assert body["artifact_ids"] == []

    types = [e["event_type"] for e in client.get(f"/api/v1/jobs/{job_id}/trace").json()["events"]]
    assert types[0] == "job_created"
    assert "orchestrator_step" in types
    assert types[-1] == "job_completed"


def test_e2e_create_docx_over_http_no_stub(client):
    _install(
        [
            json.dumps({"action": "invoke_capability", "capability": "create_docx", "arguments": DOCX_ARGS}),
            json.dumps({"action": "respond", "content": "the note is ready"}),
        ]
    )
    _conv, job_id = _run_job(client, "write the approval note")

    body = _poll(client, job_id)
    assert body["status"] == "completed"
    assert len(body["artifact_ids"]) == 1

    # The artifact is downloadable via the documented route.
    art_id = body["artifact_ids"][0]
    meta = client.get(f"/api/v1/artifacts/{art_id}")
    assert meta.status_code == 200
    assert meta.json()["type"] == "docx"
    dl = client.get(f"/api/v1/artifacts/{art_id}/download")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # .docx is a zip container
    # docs/api.md: download must carry Content-Disposition: attachment with
    # the artifact's readable filename, not a bare artifact_id.
    disposition = dl.headers.get("content-disposition", "")
    assert disposition.startswith("attachment")
    assert meta.json()["filename"] in disposition

    trace_types = [e["event_type"] for e in client.get(f"/api/v1/jobs/{job_id}/trace").json()["events"]]
    for t in ("policy_decision", "tool_invoked", "artifact_created", "job_completed"):
        assert t in trace_types


def test_e2e_denial_path_over_http(client):
    caps = json.loads(json.dumps(CAPS))
    caps["capabilities"]["create_docx"]["enabled"] = False
    manager.set_test_dependencies(
        model_client=ScriptedModel(
            [
                json.dumps({"action": "invoke_capability", "capability": "create_docx", "arguments": DOCX_ARGS}),
                json.dumps({"action": "respond", "content": "I cannot create that document"}),
            ]
        ),
        registry=CapabilityRegistry(caps),
        capabilities_config=caps,
        policy_config=POLICY,
    )
    _conv, job_id = _run_job(client, "write the approval note")

    body = _poll(client, job_id)
    assert body["status"] == "completed"          # denial is handled inside the Job
    assert body["artifact_ids"] == []

    events = client.get(f"/api/v1/jobs/{job_id}/trace").json()["events"]
    pd = [e for e in events if e["event_type"] == "policy_decision"]
    assert pd and pd[0]["payload"]["decision"] == "deny"
    assert not [e for e in events if e["event_type"] == "tool_invoked"]
    assert not [e for e in events if e["event_type"] == "artifact_created"]


def test_trace_equals_direct_audit_query(client):
    _install([json.dumps({"action": "respond", "content": "hi"})])
    _conv, job_id = _run_job(client, "hi")
    _poll(client, job_id)

    api_events = client.get(f"/api/v1/jobs/{job_id}/trace").json()["events"]
    db_rows = query_by_job_id(job_id)

    assert [e["event_type"] for e in api_events] == [r["event_type"] for r in db_rows]
    assert [e["timestamp"] for e in api_events] == [r["timestamp"] for r in db_rows]
    assert len(api_events) == len(db_rows)


# --------------------------------------------------------------------------- #
# Integration tier — real model, real retrieval (lights up with Tasks 12.a/12.b)
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_workflow_c_grounded_answer_real_model():
    if not os.environ.get("BULWARK_E2E_KB_SEEDED"):
        pytest.skip("needs Ollama running + a seeded knowledge base (Tasks 12.a/12.b)")

    manager.reset_test_dependencies()
    from backend.main import app

    with TestClient(app) as client:
        conv_id = client.post("/api/v1/conversations").json()["conversation_id"]
        job = client.post(
            "/api/v1/jobs",
            json={
                "conversation_id": conv_id,
                "message": "What is the approved maintenance window for the pumps?",
                "document_ids": [],
            },
        ).json()
        body = _poll(client, job["job_id"], timeout=120.0)
        assert body["status"] == "completed"
        types = [e["event_type"] for e in client.get(f"/api/v1/jobs/{job['job_id']}/trace").json()["events"]]
        assert "policy_decision" in types
        assert "tool_invoked" in types
        assert body["final_message"]
