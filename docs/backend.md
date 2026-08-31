# Backend (FastAPI)

## Proposed project structure

```
backend/
├── main.py                      # FastAPI app, router registration, startup/shutdown
├── config.py                    # loads config/*.yaml (see configuration.md)
├── requirements.txt
├── .env.example
│
├── api/                         # routers — thin, delegate to services
│   ├── conversations.py
│   ├── jobs.py
│   ├── documents.py
│   ├── artifacts.py
│   ├── knowledge_base.py
│   └── health.py
│
├── domain/                      # core business logic, framework-agnostic
│   ├── orchestrator/
│   │   ├── agent.py             # the hand-rolled agent loop (agent.md)
│   │   ├── prompt_builder.py    # builds system prompt from Capability Registry
│   │   └── proposal_parser.py   # validates the action/invoke_capability shape
│   ├── policy/
│   │   └── engine.py            # deterministic rule evaluation (security.md)
│   ├── job_manager/
│   │   └── manager.py           # Job/JobStep state, dispatch to executors
│   ├── capabilities/
│   │   ├── registry.py          # loads capabilities.md-defined contracts (as code)
│   │   ├── extract_document.py
│   │   ├── search_knowledge_base.py
│   │   ├── generate_code.py
│   │   ├── execute_code.py
│   │   ├── create_docx.py
│   │   └── create_xlsx.py
│   ├── model_runtime/
│   │   ├── runtime.py           # Ollama HTTP client wrapper — the ONLY caller of Ollama's API
│   │   └── lifecycle_manager.py # load/unload/eviction (models.md)
│   ├── rag/
│   │   ├── ingestion.py
│   │   └── retrieval.py
│   ├── document_processing/
│   │   ├── ocr.py                # PaddleOCR wrapper
│   │   ├── vision_escalation.py
│   │   └── pipeline.py           # tiering logic (document-processing.md)
│   ├── sandbox/
│   │   └── docker_executor.py    # sandbox.md
│   ├── artifacts/
│   │   ├── docx_renderer.py
│   │   └── xlsx_renderer.py
│   └── audit/
│       └── events.py             # single write path — insert + SSE broadcast (audit.md)
│
├── repositories/                 # SQLite data access, one module per entity
│   ├── conversations.py
│   ├── jobs.py
│   ├── documents.py
│   ├── artifacts.py
│   ├── audit_events.py
│   └── knowledge_base.py
│
├── models/
│   └── schemas.py                # Pydantic models — request/response and capability I/O
│
└── utils/
    ├── ids.py                    # UUID generation
    └── paths.py                  # scoped filesystem path helpers (data/uploads/, etc.)
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `api/*` | HTTP request/response only — validate, call a domain function, return. No business logic here. |
| `domain/orchestrator/agent.py` | The agent loop from `agent.md` — read context, call the reasoning model, parse the proposal, hand it to Policy. |
| `domain/policy/engine.py` | Every rule in `security.md`'s deterministic Policy section. |
| `domain/job_manager/manager.py` | The **only** module that dispatches to Executors — enforces that nothing reaches an Executor without passing through Policy first (`agent.md`'s Policy-interaction guarantee). |
| `domain/capabilities/*` | One module per capability, implementing exactly the contract in `capabilities.md`. |
| `domain/model_runtime/runtime.py` | The **only** module that calls Ollama's HTTP API. |
| `domain/model_runtime/lifecycle_manager.py` | Implements `models.md`'s load/keep-alive/eviction logic. |
| `domain/audit/events.py` | The **only** module that writes to `audit_events` — both the DB insert and the SSE push happen here, in one call, so they can't drift (`audit.md`). |
| `repositories/*` | Thin SQLite access — no business logic, just CRUD against `data-model.md`'s schema. |

## Job Manager

Owns the request lifecycle from `architecture.md`: create Job → loop (Orchestrator turn → Policy check → dispatch → record result) → terminate. This is the concrete home of the agent loop's *driving* logic — `agent.md`'s prose describes the behavior; this module is where it's implemented.

## Capability Executor layer

Each file in `domain/capabilities/` implements one capability's Executor: validate input against its schema, do the work (possibly via `model_runtime`, possibly via `sandbox`/`rag`/`document_processing`/`artifacts`), validate output against its schema, return. Called only by the Job Manager, only after a Policy `allow`.

## Policy engine

Pure functions over a proposed `(capability, arguments)` pair and the current system state — no side effects beyond returning an allow/deny decision (the audit event for that decision is fired by the caller, not by the engine itself, keeping the engine trivially testable).

## Model Runtime interface

A thin wrapper around Ollama's HTTP API (`/api/generate`, `/api/embed`, etc.) — this is the swap point if the runtime is ever changed (`decisions.md`, ADR-07's fallback). No other module imports an HTTP client to talk to a model directly.

## Lifecycle Manager

Implements the algorithm in `models.md`: resolve resource type → configured model → loaded or not → serve/load/evict as needed. Maintains the live `ResourceState` table.

## RAG service

`domain/rag/ingestion.py` and `retrieval.py`, implementing `rag.md` exactly — chunking, embedding calls (via `model_runtime`), Chroma reads/writes.

## Document processing

`domain/document_processing/pipeline.py` implements the tiered logic from `document-processing.md`; `ocr.py` and `vision_escalation.py` are the two concrete extraction backends it chooses between.

## Sandbox service

`domain/sandbox/docker_executor.py` implements `sandbox.md` exactly — the `docker run` invocation, timeout wrapping, mount setup, cleanup.

## Artifact service

`domain/artifacts/*` implement `artifacts.md` — schema validation, template rendering, atomic write to `data/artifacts/`.

## Audit service

`domain/audit/events.py` — single write path, as above.

## Repositories/storage

One module per entity in `data-model.md`, no cross-entity logic — that belongs in `domain/`.

## SSE delivery

Implemented in `api/jobs.py`'s `/events` route, subscribing to `domain/audit/events.py`'s broadcast mechanism for a given `job_id`.

## Background jobs

Knowledge-base ingestion (`POST /api/v1/knowledge-base/documents`) runs as a FastAPI `BackgroundTasks` job — no separate task queue needed at SIH scale.

## Configuration

Loaded once at startup by `config.py` from `config/*.yaml` (`configuration.md`) — no runtime reloading needed for SIH; a config change requires a restart, which is an acceptable, documented constraint.

## Dependency injection

FastAPI's native `Depends()` mechanism for repository/service wiring — no additional DI framework needed at this scope.

## Errors

Domain-layer exceptions map to the HTTP error shape in `api.md` at the `api/` router boundary — domain code raises typed exceptions (e.g., `CapabilityValidationError`, `PolicyDeniedError`), routers catch and translate them; domain code never constructs HTTP responses directly.
