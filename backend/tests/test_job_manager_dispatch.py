"""
Job Manager dispatch-loop tests (Task 15 Requirement 1 + 5).

Drives `manager.run_job` directly with a scripted `FakeModelClient` and the
`isolated_db` fixture. Covers: the direct-answer path, the real (no-stub)
`create_docx` capability path through Policy, the Policy deny path, executor
errors surfacing as failed tool-results (not crashes), the free malformed
corrective turn, and step-limit exhaustion.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import pytest

from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.job_manager import manager
from backend.models.schemas import GenerationResult
from backend.repositories import conversations as conversations_repo
from backend.repositories import jobs as jobs_repo
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
    "sections": [{"heading": "Summary", "body": "All checks passed."}],
    "metadata": {"prepared_by": "Inspector", "date": "2026-09-10"},
}


class FakeModelClient:
    def __init__(self, responses: List[str]):
        self._responses = responses
        self._i = 0
        self.calls: List[str] = []

    async def generate(self, resource_type, prompt, *, images=None, options=None) -> GenerationResult:
        self.calls.append(prompt)
        text = self._responses[self._i] if self._i < len(self._responses) else json.dumps(
            {"action": "respond", "content": "fallback"}
        )
        self._i += 1
        return GenerationResult(text=text, prompt_tokens=1, completion_tokens=1, duration_ms=1)


@pytest.fixture
def artifacts_tmp(monkeypatch, tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setattr(paths_module, "ARTIFACTS_ROOT", root)
    monkeypatch.setattr(paths_module, "artifacts_path", lambda aid, ext: root / f"{aid}{ext}")
    return root


def _install(responses, caps=CAPS, policy=POLICY):
    manager.set_test_dependencies(
        model_client=FakeModelClient(responses),
        registry=CapabilityRegistry(caps),
        capabilities_config=caps,
        policy_config=policy,
    )


@pytest.fixture(autouse=True)
def _reset():
    yield
    manager.reset_test_dependencies()


def _new_job(message="do the thing") -> str:
    conv_id = conversations_repo.create_conversation()
    return asyncio.run(manager.create_job(conv_id, message, []))


def _events(job_id):
    from backend.domain.audit.events import get_events_for_job

    return asyncio.run(get_events_for_job(job_id))


def _types(job_id):
    return [e["event_type"] for e in _events(job_id)]


# --------------------------------------------------------------------------- #

def test_direct_respond_completes(isolated_db):
    _install([json.dumps({"action": "respond", "content": "the answer"})])
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "completed"
    assert job["final_message"] == "the answer"

    types = _types(job_id)
    assert types.count("job_completed") == 1
    assert "orchestrator_step" in types
    steps = jobs_repo.list_job_steps(job_id)
    assert [s["kind"] for s in steps] == ["orchestrator_reasoning"]
    assert steps[0]["status"] == "succeeded"


def test_create_docx_real_capability_no_stub(isolated_db, artifacts_tmp):
    _install(
        [
            json.dumps({"action": "invoke_capability", "capability": "create_docx", "arguments": DOCX_ARGS}),
            json.dumps({"action": "respond", "content": "document ready"}),
        ]
    )
    job_id = _new_job("write the approval note")
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "completed"

    # Policy allow was recorded, executor ran, artifact persisted — no stubs.
    types = _types(job_id)
    assert "policy_decision" in types
    assert "tool_invoked" in types
    assert "artifact_created" in types

    steps = jobs_repo.list_job_steps(job_id)
    cap_steps = [s for s in steps if s["kind"] == "capability_invocation"]
    assert len(cap_steps) == 1 and cap_steps[0]["status"] == "succeeded"

    cap_execs = jobs_repo.list_capability_executions_by_job(job_id)
    assert len(cap_execs) == 1
    assert cap_execs[0]["policy_decision"] == "allow"
    assert cap_execs[0]["duration_ms"] is not None

    artifacts = jobs_repo.list_capability_executions_by_job  # noqa: F841  (silence lints)
    from backend.repositories.artifacts import list_artifacts_by_job

    rows = list_artifacts_by_job(job_id)
    assert len(rows) == 1
    assert (artifacts_tmp / rows[0]["storage_path"]).exists()


def test_policy_deny_blocks_execution(isolated_db, artifacts_tmp):
    caps = json.loads(json.dumps(CAPS))
    caps["capabilities"]["create_docx"]["enabled"] = False
    _install(
        [
            json.dumps({"action": "invoke_capability", "capability": "create_docx", "arguments": DOCX_ARGS}),
            json.dumps({"action": "respond", "content": "cannot produce the document"}),
        ],
        caps=caps,
    )
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "completed"

    decisions = [
        json.loads(e["payload"]) if isinstance(e["payload"], str) else e["payload"]
        for e in _events(job_id)
        if e["event_type"] == "policy_decision"
    ]
    assert decisions and decisions[0]["decision"] == "deny"
    assert "artifact_created" not in _types(job_id)
    assert "tool_invoked" not in _types(job_id)

    cap_steps = [s for s in jobs_repo.list_job_steps(job_id) if s["kind"] == "capability_invocation"]
    assert len(cap_steps) == 1 and cap_steps[0]["status"] == "denied"

    from backend.repositories.artifacts import list_artifacts_by_job

    assert list_artifacts_by_job(job_id) == []


def test_executor_error_is_failed_tool_result_not_crash(isolated_db):
    # search_knowledge_base is implemented (Task 12.b) but the knowledge_base
    # Chroma collection is empty/uninitialised in this isolated test env, which
    # is itself a defined executor failure (RetrievalError, not a stub
    # NotImplementedError) — still exercises "executor raises -> failed
    # tool-result, Job does not crash".
    _install(
        [
            json.dumps({"action": "invoke_capability", "capability": "search_knowledge_base", "arguments": {"query": "maintenance window", "top_k": 3}}),
            json.dumps({"action": "respond", "content": "answered from general knowledge"}),
        ]
    )
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "completed"  # the Job did NOT crash

    types = _types(job_id)
    assert "tool_invoked" in types
    assert "error" in types

    cap_steps = [s for s in jobs_repo.list_job_steps(job_id) if s["kind"] == "capability_invocation"]
    assert len(cap_steps) == 1 and cap_steps[0]["status"] == "failed"
    assert "RetrievalError" in (cap_steps[0]["error_message"] or "")


def test_malformed_then_corrective_turn_is_free(isolated_db):
    _install(
        [
            "this is not json at all",
            json.dumps({"action": "respond", "content": "recovered"}),
        ]
    )
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "completed"
    assert job["final_message"] == "recovered"

    steps = jobs_repo.list_job_steps(job_id)
    kinds_status = [(s["kind"], s["status"]) for s in steps]
    assert ("orchestrator_reasoning", "failed") in kinds_status
    assert ("orchestrator_reasoning", "succeeded") in kinds_status


def test_repeated_malformed_hits_step_limit(isolated_db):
    policy = {"policy": {"network_access_allowed": False, "max_job_steps": 2, "malformed_output_free_retries": 1}}
    _install(["nope"] * 10, policy=policy)
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error_code"] == "step_limit_exceeded"
    # partial trace retained
    assert "job_completed" in _types(job_id)


def test_invoke_loop_hits_step_limit(isolated_db):
    policy = {"policy": {"network_access_allowed": False, "max_job_steps": 3, "malformed_output_free_retries": 1}}
    _install(
        [json.dumps({"action": "invoke_capability", "capability": "search_knowledge_base", "arguments": {"query": "q"}})] * 10,
        policy=policy,
    )
    job_id = _new_job()
    asyncio.run(manager.run_job(job_id))

    job = jobs_repo.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error_code"] == "step_limit_exceeded"
    cap_steps = [s for s in jobs_repo.list_job_steps(job_id) if s["kind"] == "capability_invocation"]
    assert len(cap_steps) == 3  # exactly max_job_steps invocations, no more
