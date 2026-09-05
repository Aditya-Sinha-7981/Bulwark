"""
Job Manager - Job/JobStep lifecycle and driver loop.

This module owns the request lifecycle from architecture.md:
create Job -> loop (Orchestrator turn -> record step -> terminate) -> complete.

The stub Orchestrator here will be replaced by Task 10 (backend/domain/orchestrator/agent.py)
and wired in by Task 15. Do not create backend/domain/orchestrator/agent.py in this task.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.domain.audit.events import emit
from backend.repositories import jobs as jobs_repo
from backend.repositories import conversations as conversations_repo
from backend.utils.ids import new_id


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _build_orchestrator_context(job_id: str, conversation_id: str) -> Dict[str, Any]:
    """Build context for the Orchestrator (stub or real)."""
    job = jobs_repo.get_job(job_id)
    if not job:
        return {"conversation_history": [], "job_steps": []}

    messages = conversations_repo.list_messages(conversation_id)
    job_steps = jobs_repo.list_job_steps(job_id)

    return {
        "conversation_history": messages,
        "job_steps": job_steps,
        "job_input": job["input_message"],
    }


def stub_orchestrator(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stub Orchestrator - always returns a direct answer.

    Task 10 replaces this with backend/domain/orchestrator/agent.py.
    Task 15 wires the real Orchestrator in place of this stub.
    """
    job_input = context.get("job_input", "")
    return {
        "action": "respond",
        "content": f"Echo: {job_input}"
    }


async def create_job(conversation_id: str, input_message: str, document_ids: List[str]) -> str:
    """
    Create a new job and emit job_created event.

    Args:
        conversation_id: The conversation UUID.
        input_message: The triggering user message.
        document_ids: List of document UUIDs (referenced, not fetched).

    Returns:
        The new job_id.
    """
    job_id = jobs_repo.create_job(
        conversation_id=conversation_id,
        input_message=input_message,
        status="created",
    )

    await emit(
        event_type="job_created",
        component="api",
        payload={
            "conversation_id": conversation_id,
            "input_message": input_message,
        },
        job_id=job_id,
    )

    return job_id


async def run_job(job_id: str) -> None:
    """
    Driver loop for a job.

    Transitions: created -> running -> (completed | failed)
    Records job_steps and emits job_completed on termination.
    """
    start_time = time.monotonic()

    updated = jobs_repo.update_job(job_id, status="running")
    if not updated:
        return

    max_steps = settings.policy.max_job_steps
    step_count = 0

    try:
        while step_count < max_steps:
            step_count += 1

            job = jobs_repo.get_job(job_id)
            if not job:
                break

            if job["status"] in ("completed", "failed"):
                break

            context = _build_orchestrator_context(job_id, job["conversation_id"])

            proposal = stub_orchestrator(context)

            step_sequence = step_count
            step_id = jobs_repo.add_job_step(
                job_id=job_id,
                sequence=step_sequence,
                kind="orchestrator_reasoning",
                input_payload=json.dumps({"context_keys": list(context.keys())}, separators=(",", ":")),
                status="succeeded",
            )

            jobs_repo.update_job_step(
                job_step_id=step_id,
                status="succeeded",
                output_payload=json.dumps(proposal, separators=(",", ":")),
                completed_at=_now_iso(),
            )

            action = proposal.get("action")
            content = proposal.get("content")

            if action == "respond":
                if content and content.strip():
                    jobs_repo.update_job(
                        job_id=job_id,
                        status="completed",
                        final_message=content,
                        completed_at=_now_iso(),
                    )

                    conversations_repo.append_message(
                        conversation_id=job["conversation_id"],
                        role="orchestrator",
                        content=content,
                        job_id=job_id,
                    )

                    break
                else:
                    jobs_repo.update_job_step(
                        job_step_id=step_id,
                        status="failed",
                        error_message="empty respond content",
                    )
                    continue

            elif action == "invoke_capability":
                jobs_repo.update_job_step(
                    job_step_id=step_id,
                    status="failed",
                    error_message="capability invocation not implemented in stub; Task 15 will handle",
                )
                continue

            else:
                jobs_repo.update_job_step(
                    job_step_id=step_id,
                    status="failed",
                    error_message=f"unknown action: {action}",
                )
                continue

        else:
            jobs_repo.update_job(
                job_id=job_id,
                status="failed",
                error_code="step_limit_exceeded",
                error_message=f"Step limit ({max_steps}) reached without final answer",
                completed_at=_now_iso(),
            )

    except Exception as e:
        jobs_repo.update_job(
            job_id=job_id,
            status="failed",
            error_code="unrecoverable_error",
            error_message=str(e),
            completed_at=_now_iso(),
        )
        raise

    finally:
        end_time = time.monotonic()
        duration_ms = int((end_time - start_time) * 1000)

        final_job = jobs_repo.get_job(job_id)
        final_status = final_job["status"] if final_job else "failed"

        await emit(
            event_type="job_completed",
            component="job_manager",
            payload={
                "status": final_status,
                "duration_ms": duration_ms,
            },
            job_id=job_id,
        )


def ensure_conversation_exists(conversation_id: str) -> bool:
    """Check if a conversation exists (for API validation)."""
    conv = conversations_repo.get_conversation(conversation_id)
    return conv is not None