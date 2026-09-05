"""
Jobs API Router

Handles job-related endpoints including the SSE event stream.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.domain.audit.events import emit, get_events_for_job, subscribe, unsubscribe


router = APIRouter(prefix="/jobs", tags=["jobs"])


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
    queue = await subscribe(job_id)

    async def event_generator():
        try:
            if replay:
                events = await get_events_for_job(job_id)
                for event in events:
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

                    # Check for disconnect after yielding
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


@router.post("")
async def create_job(request: Request) -> dict:
    """Stub: Create a new job. Full implementation in Task 5."""
    raise HTTPException(status_code=501, detail="Not implemented - Task 5")


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    """Stub: Get job status. Full implementation in Task 5."""
    raise HTTPException(status_code=501, detail="Not implemented - Task 5")


@router.get("/{job_id}/trace")
async def get_job_trace(job_id: str) -> dict:
    """Stub: Get job trace. Full implementation in Task 5."""
    raise HTTPException(status_code=501, detail="Not implemented - Task 5")