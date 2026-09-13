# API Manual Testing Guide (Postman / curl)

> Practical companion to `docs/api.md` (the canonical contract). This file adds
> exact request bodies, validation rules, error codes, and curl examples **as
> currently implemented in `backend/api/*.py`** — verified against the code on
> 2026-09-12, not just the design doc. If this ever disagrees with `docs/api.md`,
> the code (and this file) wins per `AGENTS.md` §3 — flag the drift, don't
> silently trust the older doc.
>
> Base URL for every endpoint below: `http://127.0.0.1:8000/api/v1`
> No auth — don't add headers/tokens (deliberate, see `docs/api.md`).

---

## Error envelope (applies to every non-2xx response)

```json
{ "error": { "code": "string_error_code", "message": "human-readable", "details": {} } }
```

| Status | Meaning |
|---|---|
| 400 | Malformed request / validation failure (bad MIME type, empty file, bad metadata JSON, etc.) |
| 404 | Unknown `job_id` / `conversation_id` / `artifact_id` / `document_id` / `kb_document_id` |
| 500 | Unhandled server error (e.g. storage write failure) |
| 503 | A required resource (DB) is unavailable for **this request's own synchronous work** — narrow, see `docs/api.md` "Policy considerations" / Task 15 Requirement 7. `POST /jobs` and `POST /knowledge-base/documents` never 503 — failures surface inside the Job trace / `KnowledgeBaseDocument.status` instead. |

---

## 1. Conversations

### `POST /conversations`
Body: `{}` (ignored/empty).
```bash
curl -s -X POST localhost:8000/api/v1/conversations
```
→ `201 { "conversation_id": "uuid", "created_at": "iso8601" }`

### `GET /conversations/{conversation_id}`
```bash
curl -s localhost:8000/api/v1/conversations/<conversation_id>
```
→ `200 { conversation_id, created_at, updated_at, messages: [{message_id, conversation_id, role, content, job_id, created_at}] }`
→ `404 not_found` if unknown.

---

## 2. Jobs — the main entry point

### `POST /jobs`
```json
{ "conversation_id": "uuid", "message": "text of the user's request", "document_ids": ["uuid"] }
```
`document_ids` is optional (defaults to `[]`) — reference `document_id`s from `POST /documents` uploaded beforehand.

```bash
curl -s -X POST localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"<conv-id>","message":"What does the SOP say about X?","document_ids":[]}'
```
→ `201 { "job_id": "uuid", "status": "created", "created_at": "iso8601" }`
→ `404 not_found` if `conversation_id` doesn't exist.

**The Job then runs in a FastAPI background task** — the response returns immediately with `status: "created"`; poll `GET /jobs/{id}` for progress. This never blocks the HTTP call, even if Ollama/Docker later fail mid-job.

### `GET /jobs/{job_id}`
```bash
curl -s localhost:8000/api/v1/jobs/<job_id>
```
→ `200 { job_id, status: "created|running|completed|failed", conversation_id, created_at, updated_at, final_message, artifact_ids: [], error: {code,message}|null }`
→ `404 not_found` if unknown.

Poll this until `status` is `completed` or `failed`.

### `GET /jobs/{job_id}/trace`
Full audit-event history for the job, ordered.
```bash
curl -s localhost:8000/api/v1/jobs/<job_id>/trace
```
→ `200 { job_id, events: [{event_id, event_type, component, timestamp, payload}] }`
`event_type` ∈ `job_created | orchestrator_step | policy_decision | tool_invoked | tool_result | model_invoked | resource_loaded | resource_unloaded | artifact_created | error | job_completed | network_check`.

### `GET /jobs/{job_id}/events` (SSE — live stream)
Query param `replay` (default `true`) replays persisted events on connect before streaming new ones. The Postman VS Code extension may not render SSE cleanly — curl works too:
```bash
curl -N localhost:8000/api/v1/jobs/<job_id>/events
curl -N "localhost:8000/api/v1/jobs/<job_id>/events?replay=false"
```
Stream auto-closes after a `job_completed` or `error`-terminal event, or on client disconnect. Sends `: keep-alive` comments every 30s of silence.

---

## 3. Documents (raw uploads, referenced by a Job)

### `POST /documents`
Multipart form, field `file`.
- **Allowed MIME types:** `image/jpeg`, `image/png`, `application/pdf` (`image/jpg` is normalized to `image/jpeg`). Anything else → `400 INVALID_MIME_TYPE`.
- **Max size:** `config/capabilities.yaml` → `extract_document.max_file_size_mb` (currently 10 MB) → `400 FILE_TOO_LARGE`.
- **Empty file** → `400 EMPTY_FILE`.

```bash
curl -s -X POST localhost:8000/api/v1/documents -F "file=@/path/to/scan.png;type=image/png"
```
→ `201 { document_id, filename, content_type, size_bytes, uploaded_at }`

In Postman: set method POST, body type "form-data", add a field named exactly `file`, type "File", and select the local file.

### `GET /documents/{document_id}`
```bash
curl -s localhost:8000/api/v1/documents/<document_id>
```
→ `200` metadata (no raw bytes) or `404 DOCUMENT_NOT_FOUND` (also returned for a malformed non-UUID id, not just an unknown one).

---

## 4. Artifacts (generated files: DOCX/XLSX)

### `GET /artifacts/{artifact_id}`
```bash
curl -s localhost:8000/api/v1/artifacts/<artifact_id>
```
→ `200 { artifact_id, job_id, type: "docx|xlsx|pptx", filename, created_at, size_bytes }`
→ `404 not_found`.

Get `artifact_id`s from `GET /jobs/{id}` → `artifact_ids[]` after a job that ran `create_docx`/`create_xlsx` completes.

### `GET /artifacts/{artifact_id}/download`
```bash
curl -s -OJ localhost:8000/api/v1/artifacts/<artifact_id>/download
```
→ raw file bytes, `Content-Disposition: attachment`. `404` if the row or the on-disk file is missing.

---

## 5. Knowledge base (RAG ingestion + management)

### `POST /knowledge-base/documents`
Multipart form: field `file` (required), field `metadata` (optional — a **JSON string**, not nested form fields: `{"title": "...", "category": "..."}`).
- **Allowed:** `.txt`, `.md`, `.markdown`, `.pdf` (checked by extension **or** content-type — PDF here is text-layer extraction only, not OCR).
- Anything else → `400 INVALID_MIME_TYPE`. Empty file → `400 EMPTY_FILE`. Malformed `metadata` JSON → `400 INVALID_METADATA`.

```bash
curl -s -X POST localhost:8000/api/v1/knowledge-base/documents \
  -F "file=@/path/to/sop.txt;type=text/plain" \
  -F 'metadata={"title":"Inspection SOP","category":"safety"}'
```
→ `202 { kb_document_id, status: "ingesting" }` — ingestion (parse/chunk/embed/index) runs as a background task. Poll `GET /knowledge-base` and watch `status` flip to `ready` (or `failed`) before running a Workflow C/A job against it.

### `GET /knowledge-base`
```bash
curl -s localhost:8000/api/v1/knowledge-base
```
→ `200 { documents: [{kb_document_id, title, status: "ready|ingesting|failed", chunk_count}] }`

### `DELETE /knowledge-base/documents/{kb_document_id}`
```bash
curl -s -X DELETE localhost:8000/api/v1/knowledge-base/documents/<kb_document_id>
```
→ `200 { kb_document_id, deleted: true }` (deletes the SQLite row **and** its Chroma chunks) or `404 KB_DOCUMENT_NOT_FOUND`.

---

## 6. Health

### `GET /health`
No params. Real probes, never 503s itself:
```bash
curl -s localhost:8000/api/v1/health
```
→ `200 { status: "ok", backend: "ok", database: "ok|unavailable", model_runtime: "ok|unavailable", docker: "ok|unavailable" }`
- `database`: SQLite `SELECT 1`.
- `model_runtime`: raw TCP connect to Ollama's configured host:port (liveness only, not a real generate call).
- `docker`: `docker version -f {{.Server.Version}}` succeeds.

Use this first, every session, before testing anything else.

---

## 7. Network status (zero-egress proof)

### `GET /network-status`
```bash
curl -s localhost:8000/api/v1/network-status
```
→ `200 { external_connections_detected: false, checked_at: "iso8601", monitoring_since: "iso8601" }`
Backed by a continuous `psutil` background loop (`backend/domain/monitoring/network_monitor.py`), independent of any Job — poll this repeatedly (e.g. `watch -n2 curl ...`) while running Workflows A/B/C to demonstrate it updates live rather than being a static claim.

---

## Suggested Postman collection layout

One folder per resource, matching the sections above:
```
Bulwark API/
  Conversations/        POST create, GET by id
  Jobs/                 POST create, GET status, GET trace, GET events (SSE)
  Documents/             POST upload, GET metadata
  Artifacts/             GET metadata, GET download
  Knowledge Base/        POST ingest, GET list, DELETE
  Health & Network/       GET health, GET network-status
```
Use a Postman environment (`{{baseUrl}}`, `{{conversationId}}`, `{{jobId}}`, `{{documentId}}`, `{{kbDocumentId}}`, `{{artifactId}}`) and chain requests with a "Tests" script (`pm.environment.set("jobId", pm.response.json().job_id)`) so create → poll → fetch flows without hand-copying IDs.

A ready-made version of exactly this (all 7 folders, 18 requests, environment, fixture SOPs, and a synthetic-scan-image generator) lives in `api_testing/` — see `api_testing/README.md`.

---

## Known gaps / gotchas (verified in code, 2026-09-12)

- **No KB seed script or demo fixtures exist in the repo** — you must `POST /knowledge-base/documents` your own synthetic SOP text before Workflow A/C are testable. See the manual testing plan discussed in this session.
- **Artifact `storage_path` vs `artifact_id` mismatch (flagged, Task 14 bug):** `create_docx`/`create_xlsx` renderers write files under a pre-generated filename that differs from the `artifact_id` `create_artifact()` returns. `GET /artifacts/{id}/download` already works around this by resolving via the row's `storage_path`, so this is transparent to you as a caller — just don't assume the download filename on disk equals `{artifact_id}.docx`.
- **`documents` router 404 code is `DOCUMENT_NOT_FOUND`**, not the generic `not_found` used by `conversations`/`artifacts`/`jobs` — the error *envelope shape* is identical, only the `code` string differs per router. Don't hardcode one error code across all resources.
- Capability config (`config/capabilities.yaml`) governs some validation limits referenced above (`extract_document.max_file_size_mb` = 10 currently) — check that file if a 400 surprises you.
