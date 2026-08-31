# Implementation Plan

Dependency-ordered stages. Each stage lists objective, dependencies, expected modules/files, acceptance criteria, tests, what's parallelizable, and blockers. **SIH-critical/MVP** stages must all complete for the four demo workflows to work; **post-MVP/polish** stages can slip without threatening the core demo.

## Stage 1 — Repository/bootstrap (SIH-critical)

**Objective:** Working skeleton — backend and frontend both start, talk to each other, `GET /api/v1/health` returns `ok`.
**Dependencies:** None.
**Modules:** `backend/main.py`, `backend/config.py`, `frontend/` scaffold, `docker/` (sandbox image Dockerfile), directory structure per `deployment.md`.
**Acceptance:** Health check passes; frontend loads; no functional features yet.
**Tests:** Health-check integration test.
**Parallelizable:** Backend and frontend scaffolds can start simultaneously.
**Blockers:** None.

## Stage 2 — Configuration (SIH-critical)

**Objective:** `config/*.yaml` loading, per `configuration.md`.
**Dependencies:** Stage 1.
**Modules:** `backend/config.py`, `config/resources.yaml`, `config/capabilities.yaml`, `config/policy.yaml`, `config/app.yaml`.
**Acceptance:** Config values accessible throughout the backend; no hardcoded paths/models anywhere else.
**Tests:** Config-loading unit test; a deliberate "search for hardcoded model names outside config" check before merging later stages.
**Parallelizable:** Independent of most other stages once the shape is settled — do this early.
**Blockers:** None.

## Stage 3 — Database/data model (SIH-critical)

**Objective:** SQLite schema per `data-model.md` created and migratable.
**Dependencies:** Stage 1.
**Modules:** `repositories/*`, a schema migration script.
**Acceptance:** All tables in `data-model.md` exist; repository CRUD functions tested against a real (test) database.
**Tests:** Repository unit tests per entity.
**Parallelizable:** Yes, alongside Stage 2.
**Blockers:** None.

## Stage 4 — Audit/Event subsystem (SIH-critical)

**Objective:** Single write path (`domain/audit/events.py`) — DB insert + SSE broadcast, per `audit.md`.
**Dependencies:** Stage 3 (needs `audit_events` table).
**Modules:** `domain/audit/events.py`, `api/jobs.py`'s `/events` SSE route (stubbed until Stage 5's Job Manager exists).
**Acceptance:** Any component can fire an event; it's queryable and streamable immediately.
**Tests:** Event-write + SSE-delivery integration test.
**Parallelizable:** Build this before anything that needs to emit events (everything downstream).
**Blockers:** Stage 3.

## Stage 5 — Job system (SIH-critical)

**Objective:** Job/JobStep lifecycle per `architecture.md`'s request lifecycle — creation, status transitions, step recording — without yet dispatching to real Executors.
**Dependencies:** Stages 3, 4.
**Modules:** `domain/job_manager/manager.py`, `api/jobs.py` (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/trace`).
**Acceptance:** A Job can be created, its status/steps tracked, its trace queryable — using a stub Orchestrator that always responds directly (no capabilities yet).
**Tests:** Job lifecycle integration test.
**Parallelizable:** No — this is the backbone everything else dispatches through.
**Blockers:** Stages 3, 4.

## Stage 6 — Policy engine (SIH-critical)

**Objective:** Deterministic rule evaluation per `security.md`.
**Dependencies:** Stage 2 (policy config).
**Modules:** `domain/policy/engine.py`.
**Acceptance:** Given a proposed `(capability, arguments)`, returns correct allow/deny per the rules in `security.md`, fully unit-testable in isolation.
**Tests:** Unit tests per rule (registered/enabled check, network-access invariant, filesystem-scope check, resource-limit check).
**Parallelizable:** Yes, alongside Stages 3–5.
**Blockers:** None beyond Stage 2.

## Stage 7 — Capability contracts (SIH-critical)

**Objective:** The Capability Registry as code, plus schema validation for each capability in `capabilities.md` — inputs/outputs, no execution logic yet.
**Dependencies:** Stage 2.
**Modules:** `domain/capabilities/registry.py`, Pydantic schemas in `models/schemas.py`.
**Acceptance:** Every capability's input/output schema validates correctly against both valid and invalid example payloads.
**Tests:** Capability contract tests (`testing.md`).
**Parallelizable:** Yes.
**Blockers:** None beyond Stage 2.

## Stage 8 — Model Runtime (SIH-critical)

**Objective:** Ollama HTTP wrapper, per `models.md`.
**Dependencies:** Stage 2.
**Modules:** `domain/model_runtime/runtime.py`.
**Acceptance:** Can call `reasoning`/`code_generation`/`vision`/`embedding` resource types successfully against a running Ollama instance.
**Tests:** Integration test against real local Ollama.
**Parallelizable:** Yes.
**Blockers:** Ollama installed and models pulled (`deployment.md`).

## Stage 9 — Resource/Model Lifecycle Manager (SIH-critical)

**Objective:** Load/keep-alive/unload/eviction per `models.md`.
**Dependencies:** Stage 8.
**Modules:** `domain/model_runtime/lifecycle_manager.py`, `ResourceState` repository.
**Acceptance:** Loading a resource under simulated memory pressure correctly evicts the least-recently-used non-reasoning resource; all transitions fire `resource_loaded`/`resource_unloaded` audit events.
**Tests:** Unit tests with mocked memory-pressure signals; real-hardware validation deferred to Stage 20 (the M4 Pro memory test).
**Parallelizable:** No — depends on Stage 8.
**Blockers:** Stage 8.

## Stage 10 — Orchestrator (SIH-critical)

**Objective:** The agent loop per `agent.md` — prompt construction from the Capability Registry, proposal parsing, malformed-output handling, step-limit enforcement.
**Dependencies:** Stages 5, 6, 7, 9.
**Modules:** `domain/orchestrator/agent.py`, `prompt_builder.py`, `proposal_parser.py`.
**Acceptance:** Given a request and a set of (initially stubbed) capability results, produces correctly-formed proposals and terminates correctly; malformed-output correction works.
**Tests:** Agent tests (`testing.md`) — the Orchestrator benchmark itself runs here or slightly after, once real capabilities exist (Stage 15+).
**Parallelizable:** No — the integration point for everything above.
**Blockers:** Stages 5, 6, 7, 9.

## Stage 11 — OCR/document processing (SIH-critical)

**Objective:** Tiered extraction per `document-processing.md`.
**Dependencies:** Stages 7, 8.
**Modules:** `domain/document_processing/*`.
**Acceptance:** PaddleOCR pass runs on a clean test image; escalation triggers correctly on a deliberately degraded/handwritten test image.
**Tests:** OCR tests (`testing.md`).
**Parallelizable:** Yes, alongside Stage 12.
**Blockers:** Stages 7, 8; PaddleOCR + vision model provisioned.

## Stage 12 — RAG (SIH-critical)

**Objective:** Ingestion + retrieval per `rag.md`.
**Dependencies:** Stages 7, 8.
**Modules:** `domain/rag/*`, Chroma integration.
**Acceptance:** A seeded document is ingested, chunked, embedded, and correctly retrievable by a relevant query; an irrelevant query returns honest empty/low-relevance results.
**Tests:** RAG tests (`testing.md`).
**Parallelizable:** Yes, alongside Stage 11.
**Blockers:** Stages 7, 8.

## Stage 13 — Docker sandbox (SIH-critical)

**Objective:** `execute_code` per `sandbox.md`.
**Dependencies:** Stage 7.
**Modules:** `domain/sandbox/docker_executor.py`, `docker/Dockerfile` (sandbox image).
**Acceptance:** Known-good script executes and returns correct output; known-failing script returns correct non-zero exit; a script attempting a network call fails; timeout is enforced and hard-kills the container.
**Tests:** Sandbox tests (`testing.md`), including the network-denial verification.
**Parallelizable:** Yes, independent of Stages 11–12.
**Blockers:** Stage 7; Docker Desktop running, sandbox image built.

## Stage 14 — Artifact generation (SIH-critical)

**Objective:** `create_docx`/`create_xlsx` per `artifacts.md`.
**Dependencies:** Stage 7.
**Modules:** `domain/artifacts/*`.
**Acceptance:** Valid structured input produces a schema-correct, correctly-formatted file; invalid input is rejected before any file is written.
**Tests:** Artifact tests (`testing.md`).
**Parallelizable:** Yes, independent of Stages 11–13.
**Blockers:** Stage 7.

## Stage 15 — Backend/API integration (SIH-critical)

**Objective:** Wire everything above into the full Job Manager → Policy → Executor dispatch loop; complete the API surface in `api.md`.
**Dependencies:** Stages 10–14.
**Modules:** `api/*` (remaining routers), full `domain/job_manager/manager.py` dispatch logic.
**Acceptance:** A real end-to-end request (any of the four demo workflows) completes correctly through the actual system, not stubs.
**Tests:** API tests, end-to-end SIH workflow tests (`testing.md`).
**Parallelizable:** No — integration point.
**Blockers:** Stages 10–14.

## Stage 16 — Frontend (SIH-critical, can start earlier against a mock)

**Objective:** Full UI per `frontend.md`.
**Dependencies:** Stage 1 for scaffold; real integration needs Stage 15's API, but component development can proceed against a mocked API/SSE stream in parallel with backend work.
**Modules:** All of `frontend/src/`.
**Acceptance:** Chat, upload, live trace, artifact download, RAG evidence, and sovereignty indicator all functional against the real backend.
**Tests:** Frontend component tests; manual e2e alongside Stage 15's workflow tests.
**Parallelizable:** Yes, largely — start early against a mock, integrate once Stage 15 lands.
**Blockers:** Real integration blocked on Stage 15; component-level work is not.

## Stage 17 — Integration (SIH-critical)

**Objective:** Frontend + backend running together, all four demo workflows working end-to-end through the real UI.
**Dependencies:** Stages 15, 16.
**Acceptance:** A human can run all four demo workflows through the browser, not curl/Postman.
**Tests:** End-to-end SIH workflow tests, manual.
**Blockers:** Stages 15, 16.

## Stage 18 — Security validation (SIH-critical)

**Objective:** Zero-egress enforcement fully in place and tested per `security.md` and `deployment.md`'s offline checklist.
**Dependencies:** Stage 17.
**Acceptance:** Full offline run (networking disabled) succeeds for all four workflows; OS firewall rule configured and tested; sovereignty indicator accurate throughout.
**Tests:** Zero-egress tests, security tests (`testing.md`).
**Blockers:** Stage 17.

## Stage 19 — SIH workflows (SIH-critical)

**Objective:** Each of the four workflows validated against its exact success criteria in `demo.md`, using real/representative demo assets (synthetic report images, seeded SOPs, coding tasks).
**Dependencies:** Stage 18.
**Acceptance:** Every success criterion in `demo.md` met, repeatedly (not a single lucky run).
**Tests:** End-to-end SIH workflow tests, run multiple times per workflow.
**Blockers:** Stage 18.

## Stage 20 — Performance/memory validation (SIH-critical)

**Objective:** Execute the Orchestrator benchmark and M4 Pro memory test from `testing.md` for real, on the actual reference machine.
**Dependencies:** Stage 19 (needs real workflows to test against).
**Acceptance:** Decision rules applied; final model configuration locked in `config/resources.yaml` based on actual results, not estimates.
**Tests:** As specified in `testing.md`.
**Blockers:** Stage 19; access to the actual M4 Pro.

## Stage 21 — UI/demo polish (post-MVP)

**Objective:** Presentation quality — trace readability, sovereignty-indicator visual polish, error-state clarity, demo sequencing rehearsal.
**Dependencies:** Stage 20.
**Acceptance:** Subjective — "would present this to judges without wincing."
**Blockers:** None functional — pure polish, can slip without threatening the core demo.

---

## MVP / SIH-critical vs. post-MVP

**SIH-critical (Stages 1–20):** everything required for the four demo workflows to work reliably and provably.

**Post-MVP (Stage 21 and anything from `requirements.md`'s deferred list):** UI polish, PPTX support, reranking, multi-role auth, any production-scale concern. None of these block a working SIH demo — do not let them consume time that Stages 1–20 need.

## Traceability map

```
SIH Requirement (requirements.md)
    ↓
Architecture Component (architecture.md)
    ↓
Capability/API/Data Contract (capabilities.md / api.md / data-model.md)
    ↓
Implementation Module (backend.md / frontend.md — this file's stage breakdown)
    ↓
Test (testing.md)
    ↓
SIH Demo Outcome (demo.md)
```

Example, worked through for F9 ("carry an agentic task end-to-end: scanned report → findings → DOCX"): `requirements.md` F9 → `architecture.md`'s request lifecycle + `document-processing.md`/`rag.md`/`artifacts.md` components → `extract_document`/`search_knowledge_base`/`create_docx` contracts in `capabilities.md` → Stages 11, 12, 14, 15 in this file → OCR tests + RAG tests + artifact tests + end-to-end workflow test in `testing.md` → Workflow A in `demo.md`. Every SIH-critical requirement should trace this cleanly; if one doesn't, that's a gap to raise, not silently work around.
