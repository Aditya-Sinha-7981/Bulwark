"""
Conversations API (docs/api.md — `POST /api/v1/conversations`,
`GET /api/v1/conversations/{conversation_id}`).

A conversation is the container a Job runs inside. Messages are its ordered
history (`data-model.md#Message`); the orchestrator's final answer to each Job
is appended here as a `role: "orchestrator"` row by the Job Manager.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.repositories import conversations as conversations_repo

router = APIRouter(prefix="/conversations", tags=["conversations"])

_PREVIEW_MAX_CHARS = 120


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


@router.get("")
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    List conversations, most recently active first — backs a conversation
    history panel. No `title` field exists on Conversation
    (`docs/data-model.md`), so each entry carries a `preview` derived from
    its first message instead of a persisted title.

    Response 200:
    ```json
    { "conversations": [ { "conversation_id": "uuid", "created_at": "iso8601", "updated_at": "iso8601", "preview": "string | null", "message_count": 0 } ] }
    ```
    """
    conversations = conversations_repo.list_conversations(limit=limit, offset=offset)
    result = []
    for conv in conversations:
        first_message = conversations_repo.list_messages(conv["conversation_id"], limit=1)
        preview = None
        if first_message:
            content = first_message[0]["content"]
            preview = (
                content
                if len(content) <= _PREVIEW_MAX_CHARS
                else content[:_PREVIEW_MAX_CHARS].rstrip() + "…"
            )
        result.append(
            {
                "conversation_id": conv["conversation_id"],
                "created_at": conv["created_at"],
                "updated_at": conv["updated_at"],
                "preview": preview,
                "message_count": conversations_repo.count_messages(conv["conversation_id"]),
            }
        )
    return {"conversations": result}


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
