"""
Conversations API (docs/api.md — `POST /api/v1/conversations`,
`GET /api/v1/conversations/{conversation_id}`).

A conversation is the container a Job runs inside. Messages are its ordered
history (`data-model.md#Message`); the orchestrator's final answer to each Job
is appended here as a `role: "orchestrator"` row by the Job Manager.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.repositories import conversations as conversations_repo

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _not_found(message: str) -> dict:
    return {"error": {"code": "not_found", "message": message, "details": {}}}


@router.post("", status_code=201)
async def create_conversation() -> dict:
    """
    Request: `{}` (body ignored).
    Response 201: `{ "conversation_id": "uuid", "created_at": "iso8601" }`.
    """
    conversation_id = conversations_repo.create_conversation()
    conversation = conversations_repo.get_conversation(conversation_id)
    return {
        "conversation_id": conversation_id,
        "created_at": conversation["created_at"],
    }


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    """
    Response 200: conversation metadata + ordered `messages[]`
    (`data-model.md#Message`). 404 with the api.md envelope if unknown.
    """
    conversation = conversations_repo.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail=_not_found(f"Conversation not found: {conversation_id}"),
        )

    messages = conversations_repo.list_messages(conversation_id)
    return {
        "conversation_id": conversation["conversation_id"],
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
        "messages": [
            {
                "message_id": m["message_id"],
                "conversation_id": m["conversation_id"],
                "role": m["role"],
                "content": m["content"],
                "job_id": m["job_id"],
                "created_at": m["created_at"],
            }
            for m in messages
        ],
    }
