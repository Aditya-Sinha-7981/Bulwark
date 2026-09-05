"""
Jobs API Router

Handles job-related endpoints including the SSE event stream.
"""

import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.domain.audit.events import get_events_for_job, subscribe, unsubscribe
from backend.domain.job_manager.manager import create_job, ensure_conversation_exists, run_job
from backend.repositories import jobs as jobs_repo


router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    conversation_id: str
    message: str
    document_ids: List[str] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    conversation_id: str
    created_at: str
    updated_at: str
    final_message: Optional[str]
    artifact_ids: List[str]
    error: Optional[dict]


class TraceEvent(BaseModel):
    event_id: str
    event_type: str
    component: str
    timestamp: str
    payload: dict


class TraceResponse(BaseModel):
    job_id: str
    events: List[TraceEvent]


@router.post("", response_model=CreateJobResponse, status_code=201)
async def create_job_endpoint(
    request: CreateJobRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Create a new job — the primary entry point for a user request within a conversation.

    Request:
    {
      "conversation_id": "uuid",
      "message": "text of the user's request",
      "document_ids": ["uuid", "..."]
    }

    Response 201:
    {
      "job_id": "uuid",
      "status": "created",
      "created_at": "iso8601"
    }
    """
    if not ensure_conversation_exists(request.conversation_id):
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Conversation not found: {request.conversation_id}",
                    "details": {},
                }
            },
        )

    job_id = await create_job(
        conversation_id=request.conversation_id,
        input_message=request.message,
        document_ids=request.document_ids,
    )

    job = jobs_repo.get_job(job_id)

    background_tasks.add_task(run_job, job_id)

    return {
        "job_id": job_id,
        "status": "created",
        "created_at": job["created_at"],
    }


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> dict:
    """
    Current Job state.

    Response 200:
    {
      "job_id": "uuid",
      "status": "created | running | completed | failed",
      "conversation_id": "uuid",
      "created_at": "iso8601",
      "updated_at": "iso8601",
      "final_message": "string | null",
      "artifact_ids": ["uuid"],
      "error": { "code": "string", "message": "string" } | null
    }
    """
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Job not found: {job_id}",
                    "details": {},
                }
            },
        )

    error = None
    if job["error_code"] and job["error_message"]:
        error = {
            "code": job["error_code"],
            "message": job["error_message"],
        }

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "conversation_id": job["conversation_id"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "final_message": job["final_message"],
        "artifact_ids": [],
        "error": error,
    }


@router.get("/{job_id}/trace", response_model=TraceResponse)
async def get_job_trace(job_id: str) -> dict:
    """
    Full Job trace as of now — a filtered, ordered read of the Audit event stream scoped to this job_id.

    Response 200:
    {
      "job_id": "uuid",
      "events": [
        {
          "event_id": "uuid",
          "event_type": "job_created | orchestrator_step | policy_decision | tool_invoked | model_invoked | resource_loaded | resource_unloaded | artifact_created | error | job_completed | network_check",
          "component": "string",
          "timestamp": "iso8601",
          "payload": {}
        }
      ]
    }
    """
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Job not found: {job_id}",
                    "details": {},
                }
            },
        )

    events = await get_events_for_job(job_id)

    trace_events = []
    for event in events:
        trace_events.append(
            TraceEvent(
                event_id=event["event_id"],
                event_type=event["event_type"],
                component=event["component"],
                timestamp=event["timestamp"],
                payload=event["payload"],
            )
        )

    return {
        "job_id": job_id,
        "events": trace_events,
    }


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    replay: bool = Query(True, description="Replay persisted events on connect"),
) -> StreamingResponse:
    """
    Server-Sent Events stream for job audit events.

    Streams live AuditEvent objects for the given job_id as they occur.
    Each SSE `data:` line contains one event object (same shape as /trace).

    Args:
        job_id: The job UUID to stream events for.
        replay: If True, replay persisted events on connect (late-join).

    Returns:
        text/event-stream response.
    """
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Job not found: {job_id}",
                    "details": {},
                }
            },
        )

    queue = await subscribe(job_id)

    async def event_generator():
        try:
            terminal_event_seen = False
            if replay:
                events = await get_events_for_job(job_id)
                for event in events:
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                    if event["event_type"] in ("job_completed", "error"):
                        terminal_event_seen = True

            if terminal_event_seen:
                return

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

                    if await request.is_disconnected():
                        break

                    if event["event_type"] in ("job_completed", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

        finally:
            await unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )