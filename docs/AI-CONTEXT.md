# Bulwark — Complete Project Context (Single-File)

> **Purpose:** Consolidated context document for PPT preparation. Upload this single file to an AI chat and the assistant will have the full architecture, tech stack, requirements, demo flows, decisions, and implementation plan of the project.
>
> **Project:** Bulwark. **SIH 2026, Problem Statement SIH26117.** A sovereign, on-premise, agentic multimodal AI workbench for confidential industrial/organizational work.

---

## 1. Executive Summary

A self-hosted, air-gapped, agentic AI workbench for confidential industrial/organizational work — refineries, PSUs, defence-linked manufacturing, government offices. It runs entirely on one machine, uses multiple open-weight models auto-selected by task, calls real local tools (document extraction, code sandbox, knowledge retrieval, document generation), and can prove — live, on a network monitor, not just claim — that nothing ever leaves the machine.

**Priority order, always:**
1. Reliable SIH demonstration
2. Strong implementation quality
3. Local/offline operation
4. Demonstrable zero external egress
5. Simplicity and debuggability
6. Reasonable extensibility after SIH

**Explicitly NOT building:** Multi-user auth, multi-tenant deployment, microservices/K8s/cloud, enterprise air-gap distribution tooling, general-purpose agent framework dependency.

---

## 2. System Architecture

### Core principle
The Orchestrator **reasons; it has no execution rights.** Every capability invocation passes through a deterministic Policy gate before anything executes. Everything is recorded in a single Audit event stream that also drives the live UI trace.

### Component flow
```
User → Frontend → API/Job Layer → Orchestrator → Capability Selection
  → Policy Layer (deterministic) → Job Manager → Capability Executor
     ├── Model Runtime → Resource/Model Lifecycle Manager
     ├── RAG
     ├── OCR/Vision
     ├── Sandbox (Docker)
     └── Deterministic Artifact Generation
  → Result → Job/Audit Event → Orchestrator → Final Answer/Artifact

Cross-cutting: Audit/Event System, Zero-Egress Enforcement
```

### Components and responsibilities

| Component | Responsibility | NOT responsible for |
|---|---|---|
| Frontend | UI, uploads, live trace display, artifact download | Talking to models, tools, or Docker directly |
| API/Job Layer | Creating and tracking Jobs | Reasoning, execution |
| Orchestrator | Reasoning, proposing capabilities, consuming results, final answer | Execution of any kind |
| Policy Layer | Allow/deny every proposed capability invocation | Reasoning about what *should* be done |
| Job Manager | Job/step state, dispatch to Executors | Policy decisions |
| Capability Executors | Doing the actual work (deterministic or model-backed) | Deciding whether they're allowed to run |
| Model Runtime | Resolving a resource type to a live model instance | Knowing why a capability needs it |
| Resource/Model Lifecycle Manager | Load/keep-alive/unload/eviction | Reasoning, policy |
| RAG Pipeline | Ingestion, retrieval | Deciding when retrieval is needed (Orchestrator decides) |
| Sandbox | Isolated code execution | Anything outside a single execution's scope |
| Deterministic Artifact Generator | Rendering DOCX/XLSX from structured data | Composing the content itself |
| Audit/Event Subsystem | Recording everything | Making decisions |

### Architectural principles (locked)
- The Orchestrator reasons; it has no execution rights.
- Capabilities are explicit and declared, not inferred from free text.
- Policy is fully deterministic and sits between every proposal and its execution.
- Executors perform only approved actions.
- Models are resolved through resource types, never referenced by name in application logic.
- The Model Runtime is abstracted from the rest of the application.
- The Resource/Model Lifecycle Manager owns loading, unloading, and memory contention.
- RAG retrieval is always explicit — never automatically invoked.
- OCR is one capability with internal tiered escalation — not agent-visible sub-steps.
- The sandbox is isolated and network-denied, identically on macOS and Windows.
- Artifact generation is deterministic — models produce data, code produces files.
- Jobs are first-class execution objects.
- The Job trace is a filtered view over the Audit/Event stream — never a second log.
- Zero-egress is enforced in layers.
- The system operates fully locally/offline after provisioning.

### Request lifecycle
1. Request arrives (text + optional files) → API creates a Job, fires `job_created` audit event.
2. Orchestrator reads Job context → answers directly, or proposes a capability by name with arguments.
3. Policy Layer evaluates deterministically → `allow` or `deny`, both logged. A `deny` is returned to the Orchestrator as a failed step it can react to but not override.
4. If allowed: Job Manager creates a JobStep, dispatches to the relevant Executor.
5. Executor performs the work — possibly resolving a resource type via Model Runtime → Lifecycle Manager, possibly pure deterministic code — records resource usage, fires `tool_invoked`/`model_invoked` events.
6. Result recorded, `artifact_created`/`error` events fired, streamed to frontend (SSE), returned to Orchestrator as new context.
7. Loop continues until: final answer, step limit (default 8), or unrecoverable error.
8. Job marked `completed` or `failed`, `job_completed` event fired, artifacts linked, full trace available live and retroactively.

### Zero-egress architecture (defense in depth)
Application layer (no external-call code paths exist) → Capability layer (`network_access: false` by default) → Model Runtime layer (local-only resolution) → Sandbox layer (`--network none`) → Deployment/OS layer (firewall rule scoping backend process to loopback) → Monitoring layer (live connection monitor + `network_check` audit events, independent of any Job).

---

## 3. Locked Technology Stack

| Layer | Choice |
|---|---|
| Model runtime | Ollama (0.32.x line, MLX backend on Apple Silicon) |
| Reasoning (Orchestrator) | `qwen3.5:9b` (default; benchmark vs. `gpt-oss:20b` pending) |
| Coding | `qwen2.5-coder:7b` |
| Vision | `qwen3.5:9b` (same model as reasoning) |
| Embedding | `qwen3-embedding:0.6b` |
| OCR | PaddleOCR PP-OCRv6 (CPU) |
| Vector store | Chroma |
| Agent implementation | Hand-rolled Python loop (no framework) |
| Sandbox | Docker Desktop — identical on macOS and Windows |
| Database | SQLite |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite + Tailwind |
| Artifact generation | python-docx, openpyxl |
| Event streaming | Server-Sent Events (SSE) |

**Key facts:**
- Capabilities never reference a model name. They declare a **resource type** (`reasoning`, `code_generation`, `vision`, `embedding`); the Resource/Model Configuration Registry (`config/resources.yaml`) resolves that to the configured model.
- Changing a model is a config edit + `ollama pull` — **never** application code change.
- Reasoning and vision share `qwen3.5:9b` in the current config — one loaded instance serves both.

### Reference hardware
**Primary/guaranteed SIH showcase machine:** MacBook Pro, Apple M4 Pro, 24GB unified memory, 512GB SSD. Team dev machines vary (Windows, NVIDIA 6GB VRAM, integrated-graphics-only). Application stays hardware-agnostic at the Model Runtime boundary.

---

## 4. Requirements

### Functional requirements

| ID | Requirement | Architectural home |
|---|---|---|
| F1 | Auto-select the right model for a given task, demonstrable across ≥2 task types | Capability Registry, Model Runtime, Lifecycle Manager |
| F2 | Add a new open-weight model without redesigning the system | Resource/Model Configuration Registry |
| F3 | Plan and carry out multi-step work, not single-shot replies | Orchestrator, Job Manager |
| F4 | Call local tools: file read/write, sandboxed code execution, document search, document generation | Capability Executors |
| F5 | Handle scanned PDFs, handwritten notes, photographs via OCR/vision | Document-extraction capability, tiered |
| F6 | Produce real deliverables (approval notes, Word/Excel, verified code) | Artifact Generator, Sandbox |
| F7 | Ground responses in organization documents via local knowledge base | RAG pipeline |
| F8 | Demonstrate model auto-selection across ≥2 task types, live | Demo workflows A + B |
| F9 | Carry an agentic task end-to-end: scanned report → findings → DOCX | Demo workflow A |
| F10 | Run and verify a coding task in a sandbox | Demo workflow B |
| F11 | Multimodal (image/scanned) understanding | Demo workflow A |
| F12 | Show through logs/visible monitor that no external calls occur | Demo D, zero-egress |

### Non-functional requirements
- N1: Runs entirely on one machine — no cloud dependency at runtime.
- N2: Runs on M4 Pro, 24GB with comfortable headroom.
- N3: Model swaps and multi-step execution stay within demo-acceptable latency.
- N4: Every significant action is auditable after the fact.
- N5: Policy enforcement cannot be bypassed by Orchestrator.
- N6: Code execution is isolated, network-denied, resource-limited, cleaned up after every run.
- N7: System operates fully offline after one-time provisioning.
- N8: Model/capability/config choices swappable without application rewrites.

### Sovereignty requirements
- No code path may make an external HTTP call at runtime — verified at code review.
- All models/OCR/embedding weights downloaded once; system runs with networking disabled.
- Zero-egress layered (app, capability, runtime, sandbox, OS/deployment, monitoring) — never a single mechanism.
- Live, visible zero-egress proof is first-class demo requirement.

### Supported inputs: text chat requests, scanned document images/PDFs, handwritten note images, coding requests (text).

### Supported outputs: chat responses (grounded with retrieval evidence), DOCX, XLSX, executed verified code + output, live Job trace / Audit view.

### Acceptance criteria
A requirement is "done" when: (1) its contract exists in the relevant docs file, (2) it's implemented per that contract, (3) it has a corresponding test, (4) if part of a demo workflow, it passes the exact success criteria in the demo file.

---

## 5. Capabilities (Orchestrator-Invokable Contracts)

Every capability declares name, purpose, resource_type, permissions, network_access (always false), filesystem_scope, timeout_seconds, retry_policy. Capability names here are **canonical** — used identically in the Registry, Orchestrator's proposal schema, Policy rules, and Audit events.

### 5.1 `extract_document`
- **Purpose:** Extract text/structured content from uploaded document image (scanned report, handwritten note, photo). Internally tiered (OCR → vision escalation — invisible to Orchestrator).
- **Resource type:** `vision` (only when internal escalation triggers)
- **Input:** `{ "document_id": "uuid" }`
- **Output:** `{ "extracted_text": "string", "extraction_method": "ocr | vision_escalation", "confidence": 0.0, "warnings": ["string"] }`
- **Permissions:** read `data/uploads/{document_id}`
- **Timeout:** 60s (OCR), up to 120s total with escalation

### 5.2 `search_knowledge_base`
- **Purpose:** Explicit retrieval against local knowledge base.
- **Resource type:** `embedding`
- **Input:** `{ "query": "string", "top_k": 5 }`
- **Output:** `{ "results": [{ "kb_document_id": "uuid", "title": "string", "chunk_text": "string", "score": 0.0 }] }`
- **Timeout:** 10s. Empty knowledge base or no-relevant-results = empty `results[]`, not error.

### 5.3 `generate_code`
- **Purpose:** Produce code for a described task. Does not execute.
- **Resource type:** `code_generation`
- **Input:** `{ "task_description": "string", "language": "python" }`
- **Output:** `{ "code": "string", "language": "python", "explanation": "string" }`
- **Timeout:** 30s

### 5.4 `execute_code`
- **Purpose:** Run generated code in isolated Docker sandbox.
- **Resource type:** null (deterministic)
- **Input:** `{ "code": "string", "language": "python", "input_files": ["document_id", "..."] }`
- **Output:** `{ "stdout": "string", "stderr": "string", "exit_code": 0, "timed_out": false, "output_files": ["artifact_id", "..."] }`
- **Network:** `false` enforced by `--network none` at Docker level
- **Timeout:** 30s default, hard-killed on expiry

### 5.5 `create_docx`
- **Purpose:** Deterministically render Word document from structured findings.
- **Resource type:** null (deterministic)
- **Input:** `{ "title": "string", "sections": [{"heading": "string", "body": "string"}], "metadata": {"prepared_by": "string", "date": "iso8601"} }`
- **Output:** `{ "artifact_id": "uuid", "filename": "string" }`

### 5.6 `create_xlsx`
- Same shape as `create_docx` with sheets/headers/rows. Not exercised by any SIH demo workflow — included for completeness.

### 5.7 `create_pptx` (deferred)
Same shape as `create_docx`. Declared for registry completeness; not built unless a demo workflow requires it.

### Orchestrator proposal format (only two valid `action` values)
```json
{ "action": "invoke_capability", "capability": "<name>", "arguments": { ... } }
```
or
```json
{ "action": "respond", "content": "string" }
```

---

## 6. Orchestrator & Agent Loop

### Responsibilities
Understand the request; decide direct-answer vs. capability invocation; produce a valid capability proposal; consume the result; decide whether another step is needed; produce the final answer; produce structured findings where a downstream capability (e.g. `create_docx`) requires them.

### System prompt must communicate
1. Role and scope.
2. Full list of available capabilities (name, purpose, input schema) — generated from Capability Registry, not hand-maintained.
3. The exact proposal format — no other output format acceptable.
4. That retrieval (`search_knowledge_base`) must be **explicitly proposed** when grounding is needed — never automatic.
5. That a Policy denial is final — react (explain, try a different approach), never assume it can be bypassed or retried identically.
6. Step limit (8 default) and that it must converge, not loop.

### Multi-step execution
- Default step limit: **8** capability invocations per Job (configurable).
- Each successful or failed invocation counts; Policy denials also count.
- Step limit reached without final answer → Job marked `failed` with `error_code: step_limit_exceeded`.
- **100% correct termination** — no exceptions tolerated (hard-required benchmark pass criterion).

### Termination conditions
A Job terminates when: (1) Orchestrator proposes `action: respond`, (2) step limit reached, (3) unrecoverable error.

### Malformed output handling
If Orchestrator output doesn't parse as one of two valid shapes, or references an unknown capability, or fails schema validation: rejected before Policy. Recorded as failed `JobStep`, Orchestrator gets **one** corrective turn (the only exception to "every proposal counts"), then counts fully against limit.

### RAG interaction
Orchestrator interacts with retrieval exactly like any capability — propose `search_knowledge_base`, receive results in standard tool-result shape, decide whether results are sufficient. **Never automatic** (ADR-03).

### Policy interaction — structural enforcement
The Orchestrator's only mechanism for causing effect is emitting an `invoke_capability` proposal (JSON data, not code). Backend does exactly one thing with it: pass to Policy. There is **no code path** from "Orchestrator output" → "Executor runs" that does not pass through Policy. Enforced structurally — Job Manager only calls Executors via post-Policy dispatch; no other caller exists.

---

## 7. Data Model (SQLite)

### Entities

| Entity | Purpose | Key fields |
|---|---|---|
| Conversation | Top-level user chat thread | conversation_id (PK), created_at, updated_at |
| Message | Chat message | message_id (PK), conversation_id (FK), role (`user`\|`orchestrator`), content, job_id (nullable FK), created_at |
| Job | First-class execution object | job_id (PK), conversation_id (FK), status (`created`\|`running`\|`completed`\|`failed`), input_message, final_message, error_code, error_message, timestamps |
| JobStep | One orchestrator or capability step | job_step_id (PK), job_id (FK), sequence, kind (`orchestrator_reasoning`\|`capability_invocation`), capability_name, status, input_payload (JSON), output_payload (JSON), error_message, timestamps |
| Document | Uploaded input file | document_id (PK), filename, content_type, size_bytes, storage_path (`data/uploads/`), uploaded_at |
| Artifact | Generated output file | artifact_id (PK), job_id (FK), type (`docx`\|`xlsx`\|`pptx`), filename, storage_path, size_bytes, created_at |
| CapabilityExecution | Per-capability detailed record | capability_execution_id (PK), job_step_id (FK), capability_name, resource_type, policy_decision (`allow`\|`deny`), policy_reason, duration_ms |
| ModelExecution | Per-model-call record | model_execution_id (PK), capability_execution_id (FK), resource_type, model_identifier, runtime (`ollama`), prompt_tokens, completion_tokens, duration_ms, load_triggered |
| AuditEvent | Single source of truth | event_id (PK), job_id (nullable), event_type, component, timestamp, payload (JSON) |
| ResourceState | Live model load state | resource_type (PK), model_identifier, status (`unloaded`\|`loading`\|`loaded`), loaded_at, last_used_at |
| KnowledgeBaseDocument | KB source doc | kb_document_id (PK), title, category, status (`ingesting`\|`ready`\|`failed`), storage_path, chunk_count, ingested_at |

**Critical rule:** AuditEvent is single source of truth. JobStep, CapabilityExecution, ModelExecution exist for efficient structured querying, but nothing about "what happened" should ever be tracked in a way that could disagree with the AuditEvent stream. The Job trace is a query over AuditEvent, not over JobStep.

### No retention/deletion for SIH hackathon scale.

---

## 8. Audit / Event Subsystem

**Principle:** AuditEvent is the single source of truth. The Job trace shown live in frontend is a filtered view over this stream, scoped to `job_id` — never a separately maintained log.

### Event types

| Event type | Fired by | Payload |
|---|---|---|
| `job_created` | API/Job Layer | conversation_id, input_message |
| `orchestrator_step` | Orchestrator dispatch code | action, raw proposal |
| `policy_decision` | Policy Layer | capability, decision (allow/deny), reason |
| `tool_invoked` | Job Manager on dispatch | capability, arguments |
| `model_invoked` | Model Runtime | resource_type, model_identifier, prompt_tokens, completion_tokens, duration_ms |
| `resource_loaded` | Lifecycle Manager | resource_type, model_identifier, duration_ms |
| `resource_unloaded` | Lifecycle Manager | resource_type, model_identifier, reason (idle_timeout/evicted) |
| `artifact_created` | Artifact Executor | artifact_id, type, filename |
| `error` | any component | component, message, context |
| `job_completed` | Job Manager | status, duration_ms |
| `network_check` | Monitoring component | external_connections_detected (bool), checked_at |

`job_id` is null only for Job-independent events (currently just `network_check`).

**Implementation:** the event-write function (called by every component) both inserts the row AND pushes to any open SSE subscriptions for that `job_id` — single write path, no drift.

---

## 9. Security & Sovereignty

### Zero-egress enforcement (six layers)
1. **Application:** No HTTP client call to non-localhost exists anywhere — verified at code review.
2. **Capability:** Every capability declares `network_access: false` — explicit invariant.
3. **Model Runtime:** Ollama resolved only to `localhost`.
4. **Sandbox:** Docker `--network none` — kernel-enforced.
5. **Deployment/OS:** Host firewall configured during provisioning to block outbound from backend except loopback. Set up and tested before demo day, never live-adjusted.
6. **Application (backstop):** Socket-wrapper guard rejecting non-loopback — last layer, not primary.

### Zero-egress proof
- **Live:** Backend `psutil`-based monitor → `network_check` audit events → frontend sovereignty indicator panel (`GET /api/v1/network-status`). Independent of any Job, runs the whole session.
- **Retroactive:** Every AuditEvent for model/tool invocation is queryable; none should show non-declared network access.

### Trust boundaries
- **Orchestrator ↔ Policy:** Orchestrator proposes; zero execution authority. Structural enforcement (only one dispatch function exists, only Policy-approved calls reach it).
- **Policy ↔ Executor:** Policy permits; Executors act only on permitted proposals.
- **Frontend ↔ Backend:** Frontend talks only to API layer — never models/Docker/filesystem.
- **Sandbox ↔ Host:** Filesystem and network isolated except two explicit mounts.

### Deterministic Policy (ADR-02)
Fully rule-based — never model judgment. Rules:
- Capability is registered and enabled.
- `network_access: false` invariant holds.
- Filesystem access within capability's declared scope.
- Resource limits (timeout, output size) within configured bounds.
- Every decision (allow/deny) is a `policy_decision` audit event including the specific rule that fired.

### Prompt injection
Extracted document content passed as tool-result *data*, not system-level instruction. System prompt must state that `extract_document`/`search_knowledge_base` results are untrusted data, not instructions. Prompt-engineering control, not hard boundary — known, partially-mitigated risk appropriate for SIH scope.

### Failure-safe
Every documented failure returns structured result to Orchestrator rather than crashing or silently succeeding with bad data. Nothing fails open with respect to network.

---

## 10. Sandbox (Docker)

**Principle:** One Sandbox contract (`execute_code`), one implementation (Docker), used identically on M4 Pro reference and every Windows dev machine. No OS-specific application logic.

### Container per invocation
```
docker run --rm \
  --network none \
  --cpus 1 --memory 512m \
  --read-only \
  -v data/sandbox/{execution_id}/input:/workspace/input:ro \
  -v data/sandbox/{execution_id}/output:/workspace/output:rw \
  --workdir /workspace \
  bulwark-sandbox:latest \
  python input/script.py
```

### Key properties
- **Image:** `bulwark-sandbox:latest` built locally during provisioning — never pulled at runtime.
- **Network denial:** `--network none` — Docker-enforced.
- **Filesystem:** `--read-only` except output mount.
- **CPU/Memory:** 1 CPU, 512MB (configurable).
- **Timeout:** 30s default, enforced by calling process with `docker kill` fallback on expiry.
- **Cleanup:** `--rm` removes container; temp dir under `data/sandbox/{execution_id}/` deleted after results captured.
- **Packages:** Only those baked into image at build time. No runtime install (would need network).

### Failure recovery
Container crash, timeout, Docker daemon unavailable → structured failed result to Orchestrator (never unhandled exception).

---

## 11. Document Processing (OCR/Vision)

### Principle
Orchestrator sees exactly **one capability** — `extract_document`. All tiering happens inside; never exposed as separate Orchestrator-visible steps (ADR-04).

### Pipeline
1. **Primary pass — PaddleOCR PP-OCRv6, CPU.** Always runs. Produces text, per-region confidence, layout structure.
2. **Quality assessment — multiple signals** (not one confidence number):
   - Mean recognition confidence
   - Detected handwriting-style regions
   - Extraction completeness (text density vs. expected)
   - Layout complexity flags (multi-column/table misreads)
3. **Escalation decision:** If ANY signal crosses configured threshold, escalate that specific image to `vision` resource type.
4. **Vision escalation:** `qwen3.5:9b` given the image directly, prompted to transcribe.
5. **Result assembly:** Returns `extraction_method`, final `extracted_text`, overall `confidence`, `warnings`.

### Output
```json
{
  "extraction_method": "ocr | vision_escalation",
  "extracted_text": "string",
  "confidence": 0.0,
  "signals": { "mean_ocr_confidence": 0.0, "handwriting_detected": false, "completeness_estimate": 0.0, "layout_complexity_flag": false },
  "warnings": ["string"]
}
```

### Limits & failures
- Max input: 10MB, 120s total processing (configurable).
- Corrupt file → clean failed result, never silent empty.
- Low confidence even after escalation → status succeeded with prominent warnings; Orchestrator decides whether to proceed.
- Vision model unavailable → falls back to OCR-only result with warning, not hard fail.

---

## 12. RAG Pipeline

**Principle:** Invoked only when Orchestrator explicitly proposes `search_knowledge_base` — never automatic (ADR-03).

### Ingestion
1. Parse (plain text/markdown; PDF text-layer extraction for clean PDFs).
2. Chunk (~500 tokens, ~50 overlap). Simple, no semantic chunking.
3. Metadata tag (kb_document_id, title, category, chunk_index).
4. Embed via `embedding` resource type (`qwen3-embedding:0.6b`).
5. Index to Chroma, collection `knowledge_base`.
6. `KnowledgeBaseDocument.status`: ingesting → ready (or failed).

### Retrieval (on Orchestrator proposal)
1. Embed query.
2. Vector similarity against Chroma, `top_k` (default 5).
3. Return `{ kb_document_id, title, chunk_text, score }`. No reranking (add only if quality disappoints).

### Honesty over fabrication
If `results` empty or irrelevant, correct behavior is honest "I don't have grounding for that" — explicitly tested as Workflow C test case C2.

### Knowledge base content
Seeded with **synthetic** SOP-style documents team authors — never real organizational data. Whoever seeds KB should write realistic-looking maintenance/procedure documents, not lorem-ipsum, since Workflow C quality depends on genuinely searchable content.

---

## 13. Deterministic Artifact Generation

**Principle:** Model produces **structured data**; application code (python-docx, openpyxl) renders the file. Model never controls formatting directly (ADR-10) — hard boundary, not style preference.

### Renderer responsibilities
1. Load fixed template.
2. Populate with payload content.
3. Apply consistent formatting (fixed by template, not per-invocation).
4. Write to `data/artifacts/{artifact_id}.{ext}`.
5. Return `{ artifact_id, filename }`.

### Templates
- **DOCX:** title, metadata block, then one section per `sections[]` entry (heading + body). Single professional template.
- **XLSX:** one sheet per `sheets[]`; first row = headers, basic bold styling.
- **No PPTX for SIH unless demo workflow requires.**

### Atomic write
Renderer writes to temp path, only moves to `data/artifacts/` on full success — so a failure never leaves a broken file where the Artifact row would otherwise point.

### Storage
`data/artifacts/{artifact_id}.{ext}`. User-facing filename derived from `title` (e.g. `Approval_Note_2026-08-30.docx`).

---

## 14. API Contract

### Conventions
- Base path: `/api/v1`
- JSON request/response, except file upload (`multipart/form-data`) and download
- All IDs: UUIDv4 strings
- Timestamps: ISO 8601 UTC
- **No authentication in SIH runtime** (single-operator demo, deferred scope — deliberate documented gap).

### Error format (every non-2xx body)
```json
{ "error": { "code": "string_code", "message": "human msg", "details": {} } }
```

| Status | Meaning |
|---|---|
| 400 | Malformed request / validation failure |
| 404 | Resource not found (Job, Artifact, Document, Conversation) |
| 409 | Conflict (Job already completed, cannot cancel) |
| 422 | Policy denial (rare — most denials internal to Job trace, not HTTP) |
| 500 | Unhandled server error |
| 503 | Required resource (model/Docker/Chroma) unavailable |

### Endpoints (summary)
- `POST /api/v1/conversations` — create conversation
- `GET /api/v1/conversations/{id}` — get conversation + messages
- `POST /api/v1/jobs` — create Job (conversation_id, message, document_ids[]) → 201 with job_id
- `GET /api/v1/jobs/{id}` — current state, status, final_message, artifact_ids, error
- `GET /api/v1/jobs/{id}/trace` — full trace (filtered Audit events)
- `GET /api/v1/jobs/{id}/events` — SSE stream
- `POST /api/v1/documents` — upload file (multipart) → document_id
- `GET /api/v1/documents/{id}` — metadata
- `GET /api/v1/artifacts/{id}` — metadata
- `GET /api/v1/artifacts/{id}/download` — raw bytes
- `POST /api/v1/knowledge-base/documents` — ingest (background, returns 202)
- `GET /api/v1/knowledge-base` — list ingested KB documents
- `DELETE /api/v1/knowledge-base/documents/{id}` — remove
- `GET /api/v1/health` — status of backend, db, model_runtime, docker
- `GET /api/v1/network-status` — sovereignty proof: `{ external_connections_detected: false, checked_at, monitoring_since }`

---

## 15. Backend Project Structure (FastAPI)

```
backend/
├── main.py              # FastAPI app, startup/shutdown
├── config.py            # loads config/*.yaml
├── requirements.txt
├── api/                 # thin routers (conversations, jobs, documents, artifacts, knowledge_base, health)
├── domain/              # framework-agnostic business logic
│   ├── orchestrator/    # agent.py (hand-rolled loop), prompt_builder.py, proposal_parser.py
│   ├── policy/          # engine.py — deterministic rules
│   ├── job_manager/     # manager.py — ONLY dispatcher to Executors
│   ├── capabilities/    # registry.py + one module per capability
│   ├── model_runtime/   # runtime.py (ONLY Ollama caller), lifecycle_manager.py
│   ├── rag/             # ingestion.py, retrieval.py
│   ├── document_processing/  # ocr.py, vision_escalation.py, pipeline.py
│   ├── sandbox/         # docker_executor.py
│   ├── artifacts/       # docx_renderer.py, xlsx_renderer.py
│   └── audit/           # events.py — single write path, insert + SSE broadcast
├── repositories/        # SQLite CRUD, one per entity
├── models/schemas.py    # Pydantic schemas
└── utils/
```

### Key "only" modules (security-critical single points)
- `domain/model_runtime/runtime.py` — **only** module that calls Ollama HTTP API.
- `domain/job_manager/manager.py` — **only** module that dispatches to Executors after Policy.
- `domain/audit/events.py` — **only** module that writes to `audit_events` (insert + SSE push in one call).

---

## 16. Frontend (React + Vite + Tailwind)

### Hard rule
**Frontend never communicates with models, tools, or Docker directly.** Every interaction through API layer (`api.md`).

### Structure
```
frontend/src/
├── App.jsx, main.jsx
├── pages/Workbench.jsx        # single-page — chat + trace + artifacts
├── components/
│   ├── ChatPanel.jsx          # history + input + upload
│   ├── JobTracePanel.jsx      # live execution trace (SSE-driven)
│   ├── CapabilityActivity.jsx # one trace event renderer
│   ├── ArtifactPanel.jsx      # generated files + download
│   ├── RagEvidencePanel.jsx   # retrieval results visible
│   ├── SovereigntyIndicator.jsx # network-status panel
│   ├── UploadButton.jsx
│   └── ErrorBanner.jsx
├── hooks/
│   ├── useJobEvents.js        # SSE subscription
│   └── useApi.js
└── services/api.js            # one function per api.md endpoint
```

### Chat flow
`ChatPanel`: history via `GET /conversations/{id}`, submit creates Job (`POST /jobs`), immediately opens trace panel for that job_id.

### Live trace
`JobTracePanel` + `useJobEvents(job_id)` → `GET /jobs/{id}/events` (SSE). On mount: fetch `/trace` (late-join), then switch to live SSE.

### Sovereignty indicator
`SovereigntyIndicator` polls `GET /network-status` every ~2s. Persistent "0 external connections" panel.

### State management
React state + the two hooks is sufficient. No additional state library needed.

---

## 17. Configuration

All configuration under `config/*.yaml`, loaded once at startup. **No secrets in SIH runtime** — no external API keys; everything local.

### `config/resources.yaml`
```yaml
resources:
  reasoning:      { model: qwen3.5:9b, runtime: ollama, context_window: 128000, keep_alive: "5m" }
  code_generation:{ model: qwen2.5-coder:7b, runtime: ollama, context_window: 32768, keep_alive: "5m" }
  vision:         { model: qwen3.5:9b, runtime: ollama, context_window: 256000, keep_alive: "5m" }
  embedding:      { model: qwen3-embedding:0.6b, runtime: ollama, keep_alive: "-1" }   # always resident
```

### `config/capabilities.yaml`
Per-capability enabled flag, timeout, resource limits (e.g. `execute_code` cpu:1, memory_mb:512, max_output_bytes:65536).

### `config/policy.yaml`
```yaml
policy:
  network_access_allowed: false   # invariant — never set true
  max_job_steps: 8
  malformed_output_free_retries: 1
```

### `config/app.yaml`
Host: `127.0.0.1`, port: `8000`, CORS `["http://localhost:5173"]`. Paths under `./data/` for uploads/extraction/artifacts/sandbox/tmp/db/chroma. OCR escalation thresholds (mean_confidence_below: 0.75, completeness_below: 0.6, handwriting_detected: true, layout_complexity_flag: true).

**No environment-specific overrides** — Ollama selects Metal/CUDA transparently per machine.

---

## 18. Models & Lifecycle Management

### Locked model stack
| Role | Resource type | Model | Context | Quant |
|---|---|---|---|---|
| Orchestrator/reasoning | `reasoning` | `qwen3.5:9b` (validated vs. `gpt-oss:20b`) | 128K | Q4_K_M |
| Coding | `code_generation` | `qwen2.5-coder:7b` | 32K | Q4_K_M |
| Vision (fallback only) | `vision` | `qwen3.5:9b` (shared with reasoning) | 256K | Q4_K_M |
| Embedding | `embedding` | `qwen3-embedding:0.6b` | n/a | default |

### Lifecycle manager responsibilities
- **Resolve:** Given resource type, lookup configured model; if loaded serve it; if not trigger load.
- **Load:** Call Ollama, fire `resource_loaded` audit event with duration.
- **Keep-alive:** Each resource's `keep_alive` controls idle window (5m default; `-1` always resident for embedding).
- **Eviction under memory pressure:** Proactively unload least-recently-used **non-reasoning** resource before new load. Reasoning evicted last.
- **Failure recovery:** Load failure → failed result to Executor, `error` event, never silent hang.
- **Audit:** All lifecycle transitions emit `resource_loaded`/`resource_unloaded`.

### M4 Pro memory budget (24GB)
| Component | Footprint |
|---|---|
| macOS + browser/editor | ~3–4GB |
| Backend + frontend dev | ~0.5–1GB |
| SQLite + Chroma | ~0.5GB |
| Docker Desktop (idle VM) | ~1–2GB |
| `embedding` (always resident) | ~1.5GB |
| `reasoning`/`vision` (`qwen3.5:9b`, shared) | ~6.6GB |
| `code_generation` (`qwen2.5-coder:7b`) if concurrent | ~5GB |

Reasoning+embedding alone ~9GB — comfortable. Reasoning+coding+embedding ~14GB — comfortable within budget. Chose `qwen3.5:9b` over larger `gpt-oss:20b` specifically for this headroom.

### Fallbacks
| Resource | Primary | Fallback | Trigger |
|---|---|---|---|
| reasoning | qwen3.5:9b | gpt-oss:20b | reliability deficit in benchmark |
| reasoning (secondary) | — | qwen3:14b | both fail |
| code_generation | qwen2.5-coder:7b | qwen3.5:4b | memory pressure |
| vision | qwen3.5:9b | qwen2-vl:7b | packaging issues |
| embedding | qwen3-embedding:0.6b | nomic-embed-text | negligible difference + memory reclaim |

---

## 19. Demo Workflows (SIH-critical)

### Workflow A — Scanned report → SOP retrieval → findings → DOCX
**Steps:**
1. Orchestrator proposes `extract_document` with uploaded document_id.
2. Reads text; proposes `search_knowledge_base` to ground against SOPs.
3. Composes structured findings.
4. Proposes `create_docx` with structured findings.
5. Responds with summary referencing artifact.

**Resource usage:** `vision` if extraction escalates, `embedding` for retrieval, `reasoning` throughout.
**Success:** Correct sequencing (extraction → retrieval → generation, not skipped/reordered), schema-valid DOCX, findings traceable to extracted text + retrieved SOP content.

### Workflow B — Coding request → generation → sandbox → verification
**Steps:**
1. Propose `generate_code`.
2. Propose `execute_code`.
3. If failed, propose corrected generate/execute pair (bounded by step limit).
4. Respond with verified result + code.

**Resource:** `code_generation` for generation; no resource for execution.
**Success:** Generation and execution as distinct audited steps; correct sandbox result interpretation; correct termination. Deliberate bug showing correction loop is a *good* demo moment if rehearsed.

### Workflow C — Local knowledge query → explicit retrieval → grounded answer
**Steps:**
1. Propose `search_knowledge_base` directly.
2. Compose grounded answer.

**Resource:** `embedding` for query, `reasoning` for composition.
**Success:** Retrieval explicit and visible in trace (never implicit); answer traceable to retrieved chunks. Honest "I don't have grounding for that" if not in KB — deliberately demonstrate once.

### Workflow D — Visible zero-egress proof
**Standing property** throughout entire session, not activated specially. `GET /network-status` continuously shows `external_connections_detected: false`. `network_check` audit events accumulate independent of any Job.

**Show judges:** (1) live panel — ideally capture during Workflow B's sandbox execution; (2) if pressed, query Audit log showing zero non-loopback connections across every `model_invoked`/`tool_invoked` event.

**Success:** Panel visibly live (not static); follow-up "how do you know?" has real answer pointing at enforcement layers + retroactive audit query.

### Recommended demo order
**C → A → B**, with D narrated continuously. C = shortest/safest opener; A = full multimodal-to-deliverable chain; B = most interactive (benefits from visible-swap/correction-loop narration). Rehearse model-swap moments (`resource_loaded` events) as a feature to point at, not a pause to apologize for.

---

## 20. Testing Strategy

### Test categories
- **Unit:** Policy rules, schema validation, artifact renderers, eviction logic.
- **Integration:** Executors against real local dependencies (Ollama, Chroma, Docker, PaddleOCR).
- **Capability contract:** Valid input → schema-valid output; invalid input rejected before execution.
- **API:** Every endpoint shape, status codes, error format.
- **Agent:** Orchestrator loop against representative conversations.
- **OCR:** Tiering — escalation triggers per signal, not just confidence number.
- **RAG:** Ingestion → retrieval round-trip; empty-result honesty.
- **Sandbox:** Known-good/failing/timeout scripts; network-denial verification.
- **Zero-egress:** Full offline run; monitor accuracy.
- **End-to-end SIH workflow:** All four demo workflows in full.

### Failure injection (explicit)
- Malformed model output (Orchestrator proposal)
- OCR failure (corrupt file)
- Model unavailable (Ollama down)
- Model load failure
- Sandbox timeout (hard kill, `timed_out: true`)
- Sandbox crash (captured non-zero exit, no unhandled exception)
- Policy denial (Orchestrator doesn't loop retrying identical call)
- Corrupted artifact write (atomic-write keeps no broken file linked)
- Missing RAG evidence (honest "no grounding", not fabrication)
- Resource exhaustion (eviction triggers per models.md, not OOM)

### Orchestrator benchmark procedure
**Candidates:** A: `qwen3.5:9b` (default) vs. B: `gpt-oss:20b`.

**Suite:** Capability-selection battery (≥20 distinct prompts, each 3× per candidate) + Workflows A/B/C with sub-tests A1–A4, B1–B4, C1–C3.

**Metrics (with thresholds):**
| Metric | Threshold |
|---|---|
| Capability selection accuracy | ≥90% |
| Malformed tool-call rate | ≤5% |
| Unnecessary tool-call rate | ≤10% |
| Missed required tool-call rate | ≤5% |
| Correct tool arguments rate | ≥90% |
| Structured-output validity | ≥95% |
| Task success rate per workflow | ≥80% |
| **Correct termination** | **100%** (hard) |

**Decision rule:**
- Select A if it clears every threshold, or within ~5 points of B on task success while clearing hard thresholds outright — memory/latency advantage settles ties.
- Select B if A fails any hard threshold or task success trails B by >10–15 points.
- Escalate to `qwen3:14b` only if both fail — flag explicitly, don't silently substitute.

### M4 Pro memory test
1. Absolute baseline (fresh boot, OS only) — record memory.
2. Realistic baseline (browser, Spotify, VS Code, terminal).
3. App-stack baseline (backend, frontend, Docker, Chroma, SQLite).
4. Resource-loaded (each model individually via Ollama).
5. Workflow-peak (each demo workflow with reasoning loaded + specialist swaps).
6. **Concurrent-load case** (reasoning + code_generation together ~14GB) — validate estimate.
7. Pressure check (memory-pressure indicator + `vm_stat` swap activity — must stay green).
8. Latency-under-load check (compare tokens/sec at step 6 vs. idle; flag >15–20% degradation).

**Acceptance:** memory pressure green throughout, zero swap, ≥2–3GB genuine headroom at peak.

---

## 21. Implementation Plan (21 Stages)

### SIH-critical stages (Stages 1–20)
1. **Repository/bootstrap** — backend + frontend start, talk, health passes.
2. **Configuration** — `config/*.yaml` loading, no hardcoded paths/models.
3. **Database/data model** — SQLite schema per data-model.md.
4. **Audit/Event subsystem** — single write path, DB + SSE.
5. **Job system** — Job/JobStep lifecycle with stub Orchestrator (no real capabilities yet).
6. **Policy engine** — deterministic rule evaluation.
7. **Capability contracts** — Registry as code, schema validation.
8. **Model Runtime** — Ollama HTTP wrapper (reasoning/code_generation/vision/embedding).
9. **Resource/Model Lifecycle Manager** — load/keep-alive/unload/eviction.
10. **Orchestrator** — agent loop, prompt construction, proposal parsing, step limit, termination.
11. **OCR/document processing** — tiered extraction (PaddleOCR + escalation).
12. **RAG** — ingestion + retrieval.
13. **Docker sandbox** — `execute_code` with isolation/network denial.
14. **Artifact generation** — `create_docx`/`create_xlsx`.
15. **Backend/API integration** — full Job Manager → Policy → Executor dispatch.
16. **Frontend** — full UI (can start earlier against mock).
17. **Integration** — frontend + backend together, all four workflows via browser.
18. **Security validation** — zero-egress enforced + tested offline.
19. **SIH workflows** — each of four validated against exact success criteria, repeatedly.
20. **Performance/memory validation** — Orchestrator benchmark + M4 Pro memory test on actual reference machine; lock final model config based on real results.

### Post-MVP (Stage 21)
- **UI/demo polish** — trace readability, sovereignty-indicator visual polish, error clarity, demo rehearsal. Can slip without threatening core demo.

**MVP/SIH-critical:** Stages 1–20 for four demo workflows working reliably and provably.
**Post-MVP:** Stage 21 + anything from requirements.md deferred list. Do not let these consume time Stages 1–20 need.

### Traceability
SIH Requirement → Architecture Component → Capability/API/Data Contract → Implementation Module → Test → SIH Demo Outcome.

Example for F9: `requirements.md` F9 → `architecture.md` request lifecycle + `document-processing.md`/`rag.md`/`artifacts.md` → `extract_document`/`search_knowledge_base`/`create_docx` contracts → Stages 11/12/14/15 → OCR + RAG + artifact + e2e workflow tests → Workflow A.

---

## 22. Security Threat Model (Brief)

| Threat | Mitigation |
|---|---|
| External network call | Six-layer defense (app/capability/runtime/sandbox/OS/monitoring) |
| Policy bypass | Structural — only one dispatch function exists, only Policy-approved calls reach it |
| Malicious uploaded document | Never executed, only OCR/vision pipeline parses; prompt-injection mitigated via system-prompt instruction treating tool data as untrusted |
| Generated code malicious | Sandbox: network-denied, resource-limited, filesystem-isolated, ephemeral |
| Resource exhaustion | Sandbox CPU/mem/timeouts; Lifecycle Manager memory-aware eviction; Job step limit 8 |
| Dependency fetches at runtime | All deps + models + OCR weights + sandbox image provisioned once while online; `.env` excluded from VCS |

---

## 23. Deployment

### Prerequisites (both platforms)
- Python 3.11+
- Node.js 20+
- Docker Desktop (latest stable)
- Ollama (latest stable, 0.32.x+)
- Git

### macOS-specific (reference/demo machine)
- Apple Silicon, recent macOS supporting Ollama MLX backend.
- Docker Desktop only (NOT Apple `container` — ADR-05 chose consistency over marginal isolation benefit).

### Windows-specific (development machines)
- Docker Desktop with WSL2 backend.
- Ollama Windows build with CUDA backend on NVIDIA GPUs.

### One-time provisioning (internet required)
1. Clone repo.
2. `cd backend && pip install -r requirements.txt`
3. `cd frontend && npm install`
4. Start Ollama, pull every model from `config/resources.yaml`:
   ```
   ollama pull qwen3.5:9b
   ollama pull qwen2.5-coder:7b
   ollama pull qwen3-embedding:0.6b
   ```
5. `pip install paddleocr` (first-run weight download).
6. Build sandbox image: `docker build -t bulwark-sandbox:latest ./sandbox`.
7. Initialize SQLite database (schema migration script).
8. Configure OS firewall rule scoping backend to loopback (one-time, documented per-platform, **never** done live).

### Startup
```
# terminal 1
ollama serve

# terminal 2
cd backend && uvicorn main:app --host 127.0.0.1 --port 8000

# terminal 3
cd frontend && npm run dev
```
Docker Desktop must be running before any `execute_code` call.

### Directory layout (created on first startup)
`data/uploads/`, `data/extraction/`, `data/artifacts/`, `data/sandbox/`, `data/tmp/`, `data/db/`, `data/chroma/`.

### Health
`GET /api/v1/health` checks backend, db, Ollama, Docker. Run after startup, before any session.

### Offline operation (explicit validation step)
After provisioning, **disconnect from network** and re-run full startup + representative request through each demo workflow. Required before SIH — not an assumption.

### SIH demo preparation checklist
- [ ] All models pulled and loadable (`ollama list`)
- [ ] Sandbox image built, test `execute_code` verified
- [ ] KB seeded with synthetic SOPs, `ready` status confirmed
- [ ] OS firewall rule configured and tested (WiFi on → no external calls; WiFi off → app still runs)
- [ ] Full offline run of all four workflows successful
- [ ] `GET /network-status` shows zero external throughout

---

## 24. Git Workflow

Simple PR-based flow:
- Start: update main → create branch (`feature/<desc>` or `fix/<desc>`).
- During: focused commits (one logical change each), meaningful messages readable without diff.
- Before push: confirm correct branch (`git status`), run tests, inspect diff + status.
- Push branch.
- Integrate via PR with summary, files changed, tests performed, screenshots if UI, known limitations, related issue.

**AI coding-agent rule:** AI agents must never work on `main`. Always: update main → branch → implement → test → review diff → commit → push → PR.

---

## 25. Architecture Decision Records (ADRs) — Summary

| ADR | Decision | Rationale |
|---|---|---|
| 01 | Capability-driven (not classifier-driven) model selection | Deterministic, demo-safe; misclassification under judges looks like broken system |
| 02 | Deterministic rule-based Policy | Auditability, explainability; can't be argued with or "reasoned around" |
| 03 | Explicit RAG (not implicit) | Visible, auditable Job step; no retrieval noise on irrelevant requests |
| 04 | Tiered OCR as one capability | Escalation logic deterministic, doesn't need agent judgment; simpler surface |
| 05 | Docker sandbox identical on macOS/Windows | Team consistency + reduced demo risk outweigh marginal Apple `container` isolation benefit |
| 06 | SQLite (not Postgres) | Zero-ops, embedded, matches single-workstation; no multi-user concurrency need |
| 07 | Ollama (not raw MLX-LM) | Simple pull/swap API; cross-platform (Metal/CUDA via Ollama) — one integration surface for team |
| 08 | Resource/Model Configuration Registry | Required by problem statement (add models later without redesign); config change vs. rewrite |
| 09 | Resource/Model Lifecycle Manager | 24GB M4 Pro cannot hold all models simultaneously; visible audited swaps rather than invisible latency causes |
| 10 | Deterministic artifact generation | Model cannot produce malformed/broken document live on stage if it never touches formatting |
| 11 | Audit as single source of truth; Job trace = filtered view | Avoids drift between live UI and retroactive audit; one source for both proofs |
| 12 | Zero-egress defense in depth | Single mechanism not defensible; layering means no single failure breaks sovereignty guarantee |
| 13 | Cross-platform application architecture | Required by team composition; reference deployment fully representative of dev machines |

---

## 26. Current Status

- **Phase 1 (architecture) — LOCKED.**
- **Phase 2 (technology/model selection) — LOCKED**, one benchmark validation pending (reasoning model: `qwen3.5:9b` vs. `gpt-oss:20b`).
- **Phase 3 (this documentation set) — COMPLETE.**
- **Implementation has NOT started.**

The Orchestrator model benchmark is a validation activity against the already-selected default (`qwen3.5:9b`) — it does not block starting implementation, since the Resource/Model Configuration Registry makes model swap a config edit, not a rewrite.

---

## 27. Key Asks / Talking Points (PPT-Friendly)

### Problem framing
"Industrial / PSU / defence / government organizations need AI assistance on confidential data — but cannot send that data to cloud APIs. We built a **fully local, fully air-gappable, fully audited** agentic workbench that demonstrates this isn't a futuristic aspiration but a working system today."

### Differentiators (one-liners)
1. **Multi-model automatic selection, no classifier in front:** Tool-based routing — a capability declares what model class it needs; Model Runtime resolves.
2. **Deterministic Policy gate:** A model cannot argue its way past a rule. Every decision is logged with the rule that fired.
3. **Zero-egress proven live, not claimed:** A standing sovereignty indicator during demos, backed by six enforcement layers and a retroactive Audit query for the doubtful.
4. **OCR self-escalates internally:** The Orchestrator proposes once; tiering (PaddleOCR → vision LLM) is the Executor's job. Simpler agent surface, better demos of "watch it fail and recover."
5. **Audit-as-truth:** Live trace + retroactive audit log are the same query. You can't write a story that disagrees with what the system logged.
6. **Same code, M4 Pro and Windows laptops:** Cross-platform by architecture, not by accident. Sandbox contract identical on both.
7. **One-PII-leaving confirmation query:** Demonstrate `psutil`-based live panel during Workflow B's sandbox execution — the moment code is running with `--network none` is when a skeptical judge wants proof.

### Demo script highlights
- Open with Workflow C (shortest, safest, establishes "I can read your SOPs and cite them").
- Move to Workflow A (showcases OCR self-escalation if scan quality requires it, ends with a real DOCX).
- Workflow B for interactive coding moment (rehearse the correction loop — a deliberate buggy first attempt is a strength if shown).
- Narrate Sovereignty Indicator throughout; on demand, show the Audit query proving zero non-loopback across every model/tool event of the session.

### Risk acknowledgments (honesty builds credibility)
- **Prompt injection from adversarial uploads:** Known partially-mitigated risk (extracted content treated as untrusted data in system prompt). Not a hard boundary. Cite as ongoing work, not solved.
- **Single-operator demo:** No auth/RBAC by design for SIH scope (explicit deferred item).
- **Reasoning model benchmark pending:** `qwen3.5:9b` is current default, validated vs. `gpt-oss:20b` per procedures in testing.md. Registry makes swap a config edit if results surprise.

### Architecture-on-a-slide
```
       ┌──────────────────┐
       │   User in UI     │
       └────────┬─────────┘
                │
   Frontend ───►│ (never talks to models/tools)
                ▼
    ┌────────────────────────────┐
    │    API / Job Layer         │
    └────────────┬───────────────┘
                 ▼
    ┌────────────────────────────┐     proposes      ┌──────────────────┐
    │  Orchestrator (LLM)        │ ────────────────► │  Policy Gate     │
    │  qwen3.5:9b                │ ◄── allow/deny ── │  (deterministic) │
    └────────────────────────────┘                   └────────┬─────────┘
                 ▲ results                                    │ allow
                 │                                            ▼
                 │                                  ┌──────────────────────┐
                 └──── tool results       ┌─────────┤  Job Manager         │
                                        │         └────────┬─────────────┘
                                        │                  │ dispatch
                                        │                  ▼
                                        │       ┌──────────────────────────────┐
                                        └───────┤ Capability Executor         │
                                                │ • extract_document          │
                                                │ • search_knowledge_base      │
                                                │ • generate_code             │
                                                │ • execute_code (Docker)     │
                                                │ • create_docx/xlsx          │
                                                └──────┬───────────────┬───────┘
                                                       │               │
                                                       ▼               ▼
                                                ┌─────────────┐  ┌──────────────┐
                                                │ Model       │  │ Audit/Event  │
                                                │ Runtime +   │  │ (single SOT) │
                                                │ Lifecycle   │  └──────┬───────┘
                                                │ (Ollama)    │         │
                                                └─────────────┘         ▼
                                                                  Frontend trace panel
                                                                  Sovereignty indicator
                                                                  Network monitor
```

### Closing one-liner
"We picked the boring architecture — hand-rolled agent loop, rule-based policy, deterministic artifacts, single audit stream — because **SIH reliability beats theoretical cleverness**, and a model that proposes rather than executes makes every action auditable by construction."
