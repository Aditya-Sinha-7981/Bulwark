# Data Model

SQLite. This file is authoritative for field names/types — other docs reference these entities, never redefine their shape.

## Entities

### Conversation

| Field | Type | Notes |
|---|---|---|
| conversation_id | TEXT (UUID) | PK |
| created_at | TEXT (ISO 8601) | |
| updated_at | TEXT (ISO 8601) | |

### Message

| Field | Type | Notes |
|---|---|---|
| message_id | TEXT (UUID) | PK |
| conversation_id | TEXT (UUID) | FK → Conversation |
| role | TEXT | `user` \| `orchestrator` |
| content | TEXT | |
| job_id | TEXT (UUID), nullable | FK → Job — set on orchestrator messages produced by a Job |
| created_at | TEXT (ISO 8601) | |

Index: `(conversation_id, created_at)`.

### Job

| Field | Type | Notes |
|---|---|---|
| job_id | TEXT (UUID) | PK |
| conversation_id | TEXT (UUID) | FK → Conversation |
| status | TEXT | `created` \| `running` \| `completed` \| `failed` |
| input_message | TEXT | the triggering user message |
| final_message | TEXT, nullable | |
| error_code | TEXT, nullable | |
| error_message | TEXT, nullable | |
| created_at | TEXT (ISO 8601) | |
| updated_at | TEXT (ISO 8601) | |
| completed_at | TEXT (ISO 8601), nullable | |

Index: `(conversation_id, created_at)`, `(status)`.

### JobStep

| Field | Type | Notes |
|---|---|---|
| job_step_id | TEXT (UUID) | PK |
| job_id | TEXT (UUID) | FK → Job |
| sequence | INTEGER | order within the Job |
| kind | TEXT | `orchestrator_reasoning` \| `capability_invocation` |
| capability_name | TEXT, nullable | set when `kind = capability_invocation` |
| status | TEXT | `pending` \| `running` \| `succeeded` \| `failed` \| `denied` |
| input_payload | TEXT (JSON) | |
| output_payload | TEXT (JSON), nullable | |
| error_message | TEXT, nullable | |
| started_at | TEXT (ISO 8601), nullable | |
| completed_at | TEXT (ISO 8601), nullable | |

Index: `(job_id, sequence)`.

### Document

Uploaded input files (not knowledge-base documents — see `KnowledgeBaseDocument` below).

| Field | Type | Notes |
|---|---|---|
| document_id | TEXT (UUID) | PK |
| filename | TEXT | |
| content_type | TEXT | |
| size_bytes | INTEGER | |
| storage_path | TEXT | relative path under `data/uploads/` |
| uploaded_at | TEXT (ISO 8601) | |

### Artifact

Generated output files.

| Field | Type | Notes |
|---|---|---|
| artifact_id | TEXT (UUID) | PK |
| job_id | TEXT (UUID) | FK → Job |
| type | TEXT | `docx` \| `xlsx` \| `pptx` |
| filename | TEXT | |
| storage_path | TEXT | relative path under `data/artifacts/` |
| size_bytes | INTEGER | |
| created_at | TEXT (ISO 8601) | |

Index: `(job_id)`.

### CapabilityExecution

One row per capability invocation — the detailed record a `JobStep` of `kind = capability_invocation` points to (kept separate from JobStep so capability-specific fields don't bloat the generic step table).

| Field | Type | Notes |
|---|---|---|
| capability_execution_id | TEXT (UUID) | PK |
| job_step_id | TEXT (UUID) | FK → JobStep |
| capability_name | TEXT | matches `capabilities.md` |
| resource_type | TEXT, nullable | `reasoning` \| `code_generation` \| `vision` \| `embedding` \| null (deterministic capability) |
| policy_decision | TEXT | `allow` \| `deny` |
| policy_reason | TEXT, nullable | set on `deny` |
| duration_ms | INTEGER, nullable | |

### ModelExecution

One row per model invocation (an Executor calling the Model Runtime).

| Field | Type | Notes |
|---|---|---|
| model_execution_id | TEXT (UUID) | PK |
| capability_execution_id | TEXT (UUID) | FK → CapabilityExecution |
| resource_type | TEXT | |
| model_identifier | TEXT | e.g. `qwen3.5:9b` |
| runtime | TEXT | `ollama` |
| prompt_tokens | INTEGER, nullable | |
| completion_tokens | INTEGER, nullable | |
| duration_ms | INTEGER, nullable | |
| load_triggered | INTEGER (bool) | whether this call triggered a fresh model load |

### AuditEvent

The single source of truth — see `audit.md` for full detail.

| Field | Type | Notes |
|---|---|---|
| event_id | TEXT (UUID) | PK |
| job_id | TEXT (UUID), nullable | null for Job-independent events (e.g. `network_check`) |
| event_type | TEXT | see `audit.md` for the full enum |
| component | TEXT | which component emitted it |
| timestamp | TEXT (ISO 8601) | |
| payload | TEXT (JSON) | |

Index: `(job_id, timestamp)`, `(event_type, timestamp)`.

### ResourceState

Current in-memory state of the Resource/Model Lifecycle Manager — a live table, not historical (history lives in AuditEvent `resource_loaded`/`resource_unloaded` events).

| Field | Type | Notes |
|---|---|---|
| resource_type | TEXT | PK |
| model_identifier | TEXT | currently configured/loaded model |
| status | TEXT | `unloaded` \| `loading` \| `loaded` |
| loaded_at | TEXT (ISO 8601), nullable | |
| last_used_at | TEXT (ISO 8601), nullable | |

### KnowledgeBaseDocument

| Field | Type | Notes |
|---|---|---|
| kb_document_id | TEXT (UUID) | PK |
| title | TEXT | |
| category | TEXT, nullable | |
| status | TEXT | `ingesting` \| `ready` \| `failed` |
| storage_path | TEXT | relative path under `data/uploads/` (source) |
| chunk_count | INTEGER | |
| ingested_at | TEXT (ISO 8601), nullable | |

Chunk-level embeddings live in Chroma, not SQLite — `KnowledgeBaseDocument.kb_document_id` is stored as chunk metadata in Chroma for correlation (see `rag.md`).

## Retention

No automatic deletion/rotation for the SIH build — hackathon data volumes don't need it. Retention policy is an explicit deferred item, not an oversight.

## Important rule

**AuditEvent is the single source of truth.** JobStep, CapabilityExecution, and ModelExecution exist for efficient structured querying (e.g., "show me this Job's steps in order" without parsing JSON payloads), but nothing about "what happened and when" should ever be tracked in a way that could disagree with the AuditEvent stream. The Job trace shown in the frontend is a query over AuditEvent, not over JobStep.
