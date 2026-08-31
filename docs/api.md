# API Contract

## Conventions

- Base path: `/api/v1`
- JSON request/response bodies, `Content-Type: application/json` except file upload (`multipart/form-data`) and download endpoints.
- All IDs are UUIDv4 strings.
- Timestamps are ISO 8601 UTC (`2026-08-30T12:34:56Z`).
- No authentication in the SIH runtime (single-operator demo — see `requirements.md` deferred scope). Do not add auth headers/tokens; this is a deliberate, documented gap, not an oversight.

## Error format

Every non-2xx response body:

```json
{
  "error": {
    "code": "string_error_code",
    "message": "human-readable message",
    "details": {}
  }
}
```

| HTTP status | Meaning |
|---|---|
| 400 | Malformed request / validation failure |
| 404 | Resource not found (Job, Artifact, Document, Conversation) |
| 409 | Conflict (e.g., Job already completed, cannot cancel) |
| 422 | Policy denial surfaced to the client (rare — most denials are internal to a Job's trace, not the HTTP layer) |
| 500 | Unhandled server error |
| 503 | A required resource (model, Docker, Chroma) is unavailable |

## Endpoints

### `POST /api/v1/conversations`

Create a new conversation.

Request: `{}`
Response `201`:
```json
{ "conversation_id": "uuid", "created_at": "iso8601" }
```

### `GET /api/v1/conversations/{conversation_id}`

Response `200`: conversation metadata + ordered `messages[]` (see `data-model.md#Message`).

### `POST /api/v1/jobs`

Create a Job — the primary entry point for a user request within a conversation.

Request:
```json
{
  "conversation_id": "uuid",
  "message": "text of the user's request",
  "document_ids": ["uuid", "..."]
}
```
`document_ids` references documents already uploaded via `POST /api/v1/documents`.

Response `201`:
```json
{ "job_id": "uuid", "status": "created", "created_at": "iso8601" }
```

### `GET /api/v1/jobs/{job_id}`

Current Job state.

Response `200`:
```json
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
```

### `GET /api/v1/jobs/{job_id}/trace`

Full Job trace as of now — a filtered, ordered read of the Audit event stream scoped to this `job_id`. Used for a non-streaming/late-join view.

Response `200`:
```json
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
```

### `GET /api/v1/jobs/{job_id}/events` (SSE)

Live stream of the same event shape as above, for this `job_id`, as they occur. `Content-Type: text/event-stream`. Each SSE `data:` line is one event object (same shape as in `/trace`). Stream closes when a `job_completed` or `error`-terminal event is sent, or the client disconnects.

### `POST /api/v1/documents`

Upload a file (multipart) for later reference by a Job.

Request: multipart form, field `file`.
Response `201`:
```json
{ "document_id": "uuid", "filename": "string", "content_type": "string", "size_bytes": 12345, "uploaded_at": "iso8601" }
```

### `GET /api/v1/documents/{document_id}`

Metadata for an uploaded document (not its raw bytes — see artifact download pattern below for retrieving bytes if needed).

### `GET /api/v1/artifacts/{artifact_id}`

Artifact metadata.

Response `200`:
```json
{
  "artifact_id": "uuid",
  "job_id": "uuid",
  "type": "docx | xlsx | pptx",
  "filename": "string",
  "created_at": "iso8601",
  "size_bytes": 12345
}
```

### `GET /api/v1/artifacts/{artifact_id}/download`

Raw file bytes, `Content-Disposition: attachment; filename="..."`.

### `POST /api/v1/knowledge-base/documents`

Ingest a document into the local knowledge base (background job — see `rag.md`).

Request: multipart form, field `file`, optional `metadata` (JSON string: `{"title": "...", "category": "..."}`).
Response `202`:
```json
{ "kb_document_id": "uuid", "status": "ingesting" }
```

### `GET /api/v1/knowledge-base`

List ingested knowledge-base documents.

Response `200`:
```json
{ "documents": [ { "kb_document_id": "uuid", "title": "string", "status": "ready | ingesting | failed", "chunk_count": 42 } ] }
```

### `DELETE /api/v1/knowledge-base/documents/{kb_document_id}`

Remove a document and its chunks from the index.

### `GET /api/v1/health`

Response `200`:
```json
{ "status": "ok", "backend": "ok", "database": "ok", "model_runtime": "ok | unavailable", "docker": "ok | unavailable" }
```

### `GET /api/v1/network-status`

The sovereignty-proof endpoint — backs the frontend's live zero-egress panel.

Response `200`:
```json
{
  "external_connections_detected": false,
  "checked_at": "iso8601",
  "monitoring_since": "iso8601"
}
```

## Policy considerations

Policy denials that occur *inside* a Job (an Orchestrator-proposed capability being denied) are not HTTP errors — they're recorded as `policy_decision` events in that Job's trace and handled by the Orchestrator within the run. HTTP-level `422` is reserved for the rare case of a request that's malformed enough to be rejected before a Job is even created.

## Stability

This contract must be stable enough for frontend and backend to be developed independently. Any change to a request/response shape here is a documentation change first, implementation change second — never the reverse.
