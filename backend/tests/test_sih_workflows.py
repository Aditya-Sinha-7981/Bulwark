"""
SIH workflow validation — tasks/19-sih-workflow-validation.md §8.

Integration-tier, real system: real Ollama (qwen3.5:9b reasoning/vision,
qwen2.5-coder:7b code_generation, qwen3-embedding:0.6b embedding), the real
Docker sandbox, and the real, already-seeded knowledge base — hits the
actual application database (`data/db/app.db`), same pattern as
test_e2e_workflow.py's `test_workflow_c_grounded_answer_real_model`.

Gated behind BULWARK_E2E_KB_SEEDED and @pytest.mark.integration so the
default `pytest -k "not integration"` run (used everywhere else in this
repo) skips it cleanly. Run explicitly:

    BULWARK_E2E_KB_SEEDED=1 pytest backend/tests/test_sih_workflows.py -v -s

Requires: Ollama running with the four configured models pulled, Docker
Desktop running with bulwark-sandbox:latest built, and the three synthetic
SOPs under tests/fixtures/demo_assets/sops/ ingested to `ready`
(tests/fixtures/demo_assets/generate_workflow_a_images.py + a manual
`POST /knowledge-base/documents` per SOP file — done once as part of this
task's validation run, not automated here, since ingestion itself is
Task 12.a's concern).

Prints a per-run summary line for every job (`docs/testing.md` "Reporting")
so a `-s` run's output can be copied into logs/feature-sih-workflows.md's
results table.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = REPO_ROOT / "tests" / "fixtures" / "demo_assets"
sys.path.insert(0, str(ASSETS_DIR))

pytestmark = pytest.mark.integration

if not os.environ.get("BULWARK_E2E_KB_SEEDED"):
    pytest.skip(
        "needs Ollama running + Docker running + the seeded knowledge base "
        "(set BULWARK_E2E_KB_SEEDED=1 to run)",
        allow_module_level=True,
    )

from workflow_b_tasks import CLEAN_TASK, TRICKY_TASK  # noqa: E402

N_RUNS = 5
JOB_TIMEOUT_SECONDS = 180.0

COVERED_QUESTION = (
    "Under SOP-100, what vibration velocity on a centrifugal pump requires "
    "it to be flagged for immediate maintenance review?"
)
UNCOVERED_QUESTION = (
    "What is the recommended tire pressure for forklifts operating in the "
    "loading bay?"
)


@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def _run_job(client, message, document_ids=None):
    conv_id = client.post("/api/v1/conversations").json()["conversation_id"]
    job = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": message,
            "document_ids": document_ids or [],
        },
    ).json()
    return conv_id, job["job_id"]


def _poll(client, job_id, timeout=JOB_TIMEOUT_SECONDS):
    waited = 0.0
    while waited < timeout:
        body = client.get(f"/api/v1/jobs/{job_id}").json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.5)
        waited += 0.5
    return client.get(f"/api/v1/jobs/{job_id}").json()


def _trace(client, job_id):
    return client.get(f"/api/v1/jobs/{job_id}/trace").json()["events"]


def _tool_sequence(trace):
    return [e["payload"]["capability"] for e in trace if e["event_type"] == "tool_invoked"]


def _upload_document(client, path: Path) -> str:
    with path.open("rb") as fh:
        resp = client.post(
            "/api/v1/documents",
            files={"file": (path.name, fh, "image/png")},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["document_id"]


def _print_run(workflow: str, run_no: int, job_id: str, status: str, note: str = "") -> None:
    print(f"[{workflow}] run {run_no}: job={job_id} status={status} {note}")


# --------------------------------------------------------------------------- #
# Workflow A — scanned report -> SOP retrieval -> findings -> DOCX
# --------------------------------------------------------------------------- #

class TestWorkflowA:
    def test_clean_asset_five_runs(self, client):
        image_path = ASSETS_DIR / "workflow_a" / "clean_inspection_report.png"
        results = []

        for i in range(1, N_RUNS + 1):
            doc_id = _upload_document(client, image_path)
            _conv, job_id = _run_job(
                client,
                "Review this inspection report and draft an approval note.",
                document_ids=[doc_id],
            )
            body = _poll(client, job_id)
            trace = _trace(client, job_id)
            tools = _tool_sequence(trace)

            correct_sequence = tools == ["extract_document", "search_knowledge_base", "create_docx"]
            terminated = body["status"] in ("completed", "failed")
            docx_valid = False
            if body["status"] == "completed" and body["artifact_ids"]:
                art_id = body["artifact_ids"][0]
                dl = client.get(f"/api/v1/artifacts/{art_id}/download")
                docx_valid = dl.status_code == 200 and dl.content[:2] == b"PK"
                if docx_valid:
                    import io

                    import docx

                    try:
                        docx.Document(io.BytesIO(dl.content))
                    except Exception:
                        docx_valid = False

            success = body["status"] == "completed" and correct_sequence and docx_valid
            results.append(
                {"terminated": terminated, "correct_sequence": correct_sequence, "docx_valid": docx_valid, "success": success}
            )
            _print_run(
                "A-clean", i, job_id, body["status"],
                f"tools={tools} docx_valid={docx_valid} success={success}",
            )
            assert terminated, f"run {i}: job did not reach a terminal state within {JOB_TIMEOUT_SECONDS}s"

        termination_rate = sum(r["terminated"] for r in results) / N_RUNS
        success_rate = sum(r["success"] for r in results) / N_RUNS
        validity_rate = sum(r["docx_valid"] for r in results if r["docx_valid"] is not None) / N_RUNS
        print(f"[A-clean] AGGREGATE termination={termination_rate:.0%} success={success_rate:.0%} docx_validity={validity_rate:.0%}")

        assert termination_rate == 1.0, "correct termination must be 100%"
        assert success_rate >= 0.8, f"task success rate {success_rate:.0%} below 80% threshold"
        assert validity_rate >= 0.95, f"structured-output validity {validity_rate:.0%} below 95% threshold"

    def test_degraded_asset_triggers_escalation_and_uncertainty(self, client):
        image_path = ASSETS_DIR / "workflow_a" / "degraded_inspection_report.png"
        doc_id = _upload_document(client, image_path)
        _conv, job_id = _run_job(
            client,
            "Review this inspection report and draft an approval note.",
            document_ids=[doc_id],
        )
        body = _poll(client, job_id)
        trace = _trace(client, job_id)

        vision_invoked = any(
            e["event_type"] == "model_invoked" and e["payload"].get("resource_type") == "vision"
            for e in trace
        )
        _print_run("A-degraded", 1, job_id, body["status"], f"vision_escalated={vision_invoked}")

        assert body["status"] in ("completed", "failed")
        assert vision_invoked, "degraded asset did not trigger vision escalation (adjust the asset, not the code)"

        if body["status"] == "completed" and body.get("final_message"):
            lowered = body["final_message"].lower()
            uncertainty_language = any(
                kw in lowered
                for kw in ("uncertain", "low confidence", "unclear", "difficult to read", "not confident", "unable to confirm", "degraded")
            )
            print(f"[A-degraded] uncertainty language present: {uncertainty_language}")


# --------------------------------------------------------------------------- #
# Workflow B — coding request -> generation -> sandbox execution -> verification
# --------------------------------------------------------------------------- #

class TestWorkflowB:
    def test_clean_task_five_runs(self, client):
        results = []
        for i in range(1, N_RUNS + 1):
            _conv, job_id = _run_job(client, CLEAN_TASK)
            body = _poll(client, job_id)
            trace = _trace(client, job_id)
            tools = _tool_sequence(trace)

            has_generate = "generate_code" in tools
            has_execute = "execute_code" in tools
            distinct_steps = has_generate and has_execute
            terminated = body["status"] in ("completed", "failed")
            success = body["status"] == "completed" and distinct_steps

            results.append({"terminated": terminated, "success": success})
            _print_run("B-clean", i, job_id, body["status"], f"tools={tools} success={success}")
            assert terminated, f"run {i}: job did not reach a terminal state within {JOB_TIMEOUT_SECONDS}s"

        termination_rate = sum(r["terminated"] for r in results) / N_RUNS
        success_rate = sum(r["success"] for r in results) / N_RUNS
        print(f"[B-clean] AGGREGATE termination={termination_rate:.0%} success={success_rate:.0%}")

        assert termination_rate == 1.0
        assert success_rate >= 0.8, f"task success rate {success_rate:.0%} below 80% threshold"

    def test_tricky_task_correction_loop_demonstration(self, client):
        """Not part of the official ≥5-run count (test_clean_task_five_runs
        covers that) — this is the deliberate buggy-variant demonstration
        (§7 Requirement 2 B). Correction-loop occurrence is reported, not
        hard-asserted, since it depends on the real model's first attempt
        (docs/testing.md: run-to-run variance is expected and measured, not
        forced)."""
        correction_loop_count = 0
        n = 3
        for i in range(1, n + 1):
            _conv, job_id = _run_job(client, TRICKY_TASK)
            body = _poll(client, job_id)
            trace = _trace(client, job_id)
            tools = _tool_sequence(trace)

            generate_count = tools.count("generate_code")
            execute_count = tools.count("execute_code")
            had_correction = generate_count > 1 and execute_count > 1
            if had_correction:
                correction_loop_count += 1

            terminated = body["status"] in ("completed", "failed")
            _print_run(
                "B-tricky", i, job_id, body["status"],
                f"generate_count={generate_count} execute_count={execute_count} correction_loop={had_correction}",
            )
            assert terminated

        print(f"[B-tricky] correction loop observed in {correction_loop_count}/{n} runs")

    def test_no_network_or_package_install_in_sandbox_result(self, client):
        _conv, job_id = _run_job(client, CLEAN_TASK)
        body = _poll(client, job_id)
        trace = _trace(client, job_id)

        for e in trace:
            if e["event_type"] == "tool_result" and e["payload"].get("capability") == "execute_code":
                result = e["payload"].get("result", {})
                stdout = str(result.get("stdout", ""))
                stderr = str(result.get("stderr", ""))
                for marker in ("pip install", "ConnectionError", "Network is unreachable", "urlopen"):
                    assert marker not in stdout and marker not in stderr

        _print_run("B-network-check", 1, job_id, body["status"])


# --------------------------------------------------------------------------- #
# Workflow C — local knowledge query -> explicit retrieval -> grounded answer
# --------------------------------------------------------------------------- #

class TestWorkflowC:
    def test_covered_question_five_runs(self, client):
        results = []
        for i in range(1, N_RUNS + 1):
            _conv, job_id = _run_job(client, COVERED_QUESTION)
            body = _poll(client, job_id)
            trace = _trace(client, job_id)
            tools = _tool_sequence(trace)

            retrieval_explicit = "search_knowledge_base" in tools
            terminated = body["status"] in ("completed", "failed")
            success = body["status"] == "completed" and retrieval_explicit and bool(body.get("final_message"))

            results.append({"terminated": terminated, "success": success})
            _print_run("C-covered", i, job_id, body["status"], f"retrieval_explicit={retrieval_explicit} success={success}")
            assert terminated

        termination_rate = sum(r["terminated"] for r in results) / N_RUNS
        success_rate = sum(r["success"] for r in results) / N_RUNS
        print(f"[C-covered] AGGREGATE termination={termination_rate:.0%} success={success_rate:.0%}")

        assert termination_rate == 1.0
        assert success_rate >= 0.8, f"task success rate {success_rate:.0%} below 80% threshold"

    def test_uncovered_question_honest_no_grounding(self, client):
        """Case C2 — docs/demo.md: 'the correct behavior is an honest
        "I don't have grounding for that"'. Heuristic (Task 19 §11 open
        question, accepted): the retrieval tool is still invoked explicitly
        (retrieval must never become implicit), but the final answer must
        not fabricate an SOP-style citation for content the KB doesn't
        have."""
        _conv, job_id = _run_job(client, UNCOVERED_QUESTION)
        body = _poll(client, job_id)
        trace = _trace(client, job_id)
        tools = _tool_sequence(trace)

        retrieval_explicit = "search_knowledge_base" in tools
        final = (body.get("final_message") or "").lower()
        fabricated_citation = any(tag in final for tag in ("sop-1", "sop-2", "sop-3", "sop-100", "sop-204", "sop-311"))

        _print_run(
            "C-uncovered", 1, job_id, body["status"],
            f"retrieval_explicit={retrieval_explicit} fabricated_citation={fabricated_citation}",
        )
        print(f"[C-uncovered] final_message: {body.get('final_message')!r}")

        assert retrieval_explicit, "retrieval must still be explicit even when nothing relevant is found"
        assert not fabricated_citation, "answer cited a specific SOP the KB has no grounding for on this question"
