"""docs/api.md contract tests for the conversations router (Task 15 Req 3)."""

import json


def test_create_conversation_201_shape(bulwark_client):
    r = bulwark_client.post("/api/v1/conversations")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"conversation_id", "created_at"}
    assert isinstance(body["conversation_id"], str) and body["conversation_id"]
    assert isinstance(body["created_at"], str) and body["created_at"]


def test_create_conversation_ignores_body(bulwark_client):
    r = bulwark_client.post("/api/v1/conversations", json={"anything": 1})
    assert r.status_code == 201


def test_get_conversation_returns_ordered_messages(bulwark_client):
    conv_id = bulwark_client.post("/api/v1/conversations").json()["conversation_id"]

    # Drive one job so the conversation has a user + orchestrator message.
    job = bulwark_client.post(
        "/api/v1/jobs",
        json={"conversation_id": conv_id, "message": "hello", "document_ids": []},
    ).json()
    _poll_job(bulwark_client, job["job_id"])

    r = bulwark_client.get(f"/api/v1/conversations/{conv_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"] == conv_id
    assert {"conversation_id", "created_at", "updated_at", "messages"} <= set(body)
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "orchestrator"]
    for m in body["messages"]:
        assert set(m) == {"message_id", "conversation_id", "role", "content", "job_id", "created_at"}
    created = [m["created_at"] for m in body["messages"]]
    assert created == sorted(created)


def test_list_conversations_most_recent_first(bulwark_client):
    older = bulwark_client.post("/api/v1/conversations").json()["conversation_id"]
    newer = bulwark_client.post("/api/v1/conversations").json()["conversation_id"]

    r = bulwark_client.get("/api/v1/conversations")
    assert r.status_code == 200
    body = r.json()
    ids = [c["conversation_id"] for c in body["conversations"]]
    assert ids.index(newer) < ids.index(older)
    for c in body["conversations"]:
        assert {"conversation_id", "created_at", "updated_at", "preview", "message_count"} <= set(c)


def test_list_conversations_preview_from_first_message(bulwark_client):
    conv_id = bulwark_client.post("/api/v1/conversations").json()["conversation_id"]
    job = bulwark_client.post(
        "/api/v1/jobs",
        json={"conversation_id": conv_id, "message": "what is the pump SOP threshold", "document_ids": []},
    ).json()
    _poll_job(bulwark_client, job["job_id"])

    r = bulwark_client.get("/api/v1/conversations")
    entry = next(c for c in r.json()["conversations"] if c["conversation_id"] == conv_id)
    assert entry["preview"] == "what is the pump SOP threshold"
    assert entry["message_count"] == 2


def test_list_conversations_respects_limit(bulwark_client):
    bulwark_client.post("/api/v1/conversations")
    bulwark_client.post("/api/v1/conversations")

    r = bulwark_client.get("/api/v1/conversations", params={"limit": 1})
    assert r.status_code == 200
    assert len(r.json()["conversations"]) == 1


def test_get_unknown_conversation_404_envelope(bulwark_client):
    r = bulwark_client.get("/api/v1/conversations/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    err = r.json()["detail"]["error"]
    assert err["code"] == "not_found"
    assert "message" in err and "details" in err


def _poll_job(client, job_id, timeout=10.0):
    import time

    waited = 0.0
    while waited < timeout:
        s = client.get(f"/api/v1/jobs/{job_id}").json()["status"]
        if s in ("completed", "failed"):
            return s
        time.sleep(0.05)
        waited += 0.05
    return None
