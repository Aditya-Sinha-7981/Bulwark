# logs/feature-rag.md

> Feature / workstream: `rag`  (branches: `feature/rag-ingestion`, …)
> Started: 2026-09-11 by Claude Sonnet 5
> Status: in-progress (ingestion half — Task 12.a — complete; retrieval — Task 12.b — not started)

## Goal

Implement the RAG ingestion pipeline and KB management API per `tasks/12a-rag-ingestion.md` (Stage 12 of `docs/implementation-plan.md`, ingestion half): accept a source document, parse → chunk → tag metadata → embed → index into Chroma (collection `knowledge_base`), track `KnowledgeBaseDocument` lifecycle, and expose `POST /api/v1/knowledge-base/documents`, `GET /api/v1/knowledge-base`, `DELETE /api/v1/knowledge-base/documents/{id}`. Retrieval + `search_knowledge_base` is Task 12.b — untouched here except for freezing the shared contract below.

## Plan

1. Read `docs/rag.md`, `docs/api.md`, `docs/data-model.md`, `docs/audit.md`, `AGENTS.md` §6 rules 5/13, and the task spec.
2. Inspect existing scaffolding: empty `domain/rag/ingestion.py` / `api/knowledge_base.py` stubs, an already-complete `repositories/knowledge_base.py` (Task 3), `domain/model_runtime/runtime.py` (`embed()` already implemented, Task 8), `utils/paths.py` (`chroma_dir()` already present, Task 2), `domain/capabilities/search_knowledge_base.py` still `NotImplementedError` (confirms Task 12.b hasn't started — safe to freeze the contract).
3. Implement `domain/rag/ingestion.py`: parsing (plain text/markdown + PDF text-layer via `pypdfium2`), deterministic character-based chunking, metadata tagging, embedding via `model_runtime.embed("embedding", ...)`, Chroma indexing, lifecycle update, failure cleanup + `error` audit event.
4. Implement `api/knowledge_base.py`: the three endpoints, `BackgroundTasks` scheduling.
5. Register the router in `main.py`; add `chromadb` to `requirements.txt` (and install it into `backend/.venv`).
6. Write `tests/test_rag_ingestion.py` with a fake embedding backend + temp Chroma dir + temp SQLite DB.
7. Discovered and fixed a contract gap in `domain/audit/events.py` (see Entry 2).

## Entries

### Entry 1 — 2026-09-11 14:30 — Ingestion pipeline + KB API implemented

**What changed:**
- `backend/domain/rag/ingestion.py` (new, was an empty stub): `parse_document()` (plain text/markdown + PDF text-layer extraction via `pypdfium2`, page texts joined with `\n\n`, no page-count limit), `chunk_text()` (deterministic, `CHUNK_SIZE_CHARS=2000` / `CHUNK_OVERLAP_CHARS=200`, character-based per the locked heuristic), `ingest_document()` (the full pipeline: parse → chunk → embed via `model_runtime.embed("embedding", chunks)` → Chroma `collection.add()` → `update_kb_document(status="ready", chunk_count, ingested_at)`), `get_chroma_client()`/`get_kb_collection()` (one process-wide `chromadb.PersistentClient` cached in a module-level global, per §10 "Known Risks" — avoids opening many clients against the same path), `delete_document_chunks()` (used by the DELETE endpoint), `_fail_ingestion()` (deletes any partial Chroma chunks for that `kb_document_id`, sets `status="failed"`, emits the `error` audit event).
- `backend/api/knowledge_base.py` (new, was an empty stub): `POST /knowledge-base/documents` (multipart `file` + optional `metadata` form field parsed as JSON `{"title", "category"}`; validates extension/content-type against `{.txt, .md, .markdown, .pdf}` / `{text/plain, text/markdown, application/pdf}`; stores the file via `uploads_path()`; creates the `KnowledgeBaseDocument` row with `status="ingesting"`; schedules `ingest_document` via `BackgroundTasks.add_task`; returns `202 {kb_document_id, status}`), `GET /knowledge-base` (documented list shape), `DELETE /knowledge-base/documents/{kb_document_id}` (404 via `get_kb_document()` check, then `delete_document_chunks()` + `delete_kb_document()`).
- `backend/main.py:9,42` — registered `knowledge_base_router` under `/api/v1`.
- `backend/requirements.txt` — added `chromadb`; installed into `backend/.venv` (chromadb 1.5.9, pulled numpy/onnxruntime/etc. as transitive deps — all local, no egress at runtime since `PersistentClient` is fully embedded/on-disk).
- `backend/tests/test_rag_ingestion.py` (new): 11 tests covering the full acceptance list in the task spec — `202` + row creation, `ingesting → ready` lifecycle, Chroma chunk metadata shape, chunk-sizing + determinism (including identical re-ingest boundaries), `GET` list shape, `DELETE` removes only the target document's chunks, `DELETE` on unknown id → `404`, unparseable file → `failed` + zero chunks, embedding failure mid-run → `failed` + zero partial chunks (verified via Chroma `collection.get(where=...)` returning empty), re-ingest → second distinct document.

**Why:** Implements `tasks/12a-rag-ingestion.md` exactly; see that file for the full contract. Frozen shared surface with Task 12.b (do not change without coordinating):
- Chroma collection name: **`knowledge_base`**
- Chunk id format: **`"{kb_document_id}:{chunk_index}"`**
- Chunk metadata fields: **`kb_document_id` (str), `title` (str), `category` (str — `""` when not provided, never `None`/absent; Chroma rejects `None` metadata values), `chunk_index` (int)**
- Chunk `documents` (Chroma's text field) holds the raw chunk text.

**How to verify:**
```bash
cd backend && .venv/bin/python -m pytest tests/test_rag_ingestion.py -q
```
11 passed. Also ran the full suite (`.venv/bin/python -m pytest -q`, excluding 4 pre-existing collection errors from missing `python-docx`/`openpyxl`/`PIL`/`psutil` in this venv — unrelated to this task, those deps were never installed here) — no regressions; see Entry 2 for the two pre-existing failures inspected and confirmed unrelated.

Manual verification (Requirement per task §8) not run in this session — requires `ollama serve` with `qwen3-embedding:0.6b` pulled, which isn't available in this sandboxed environment. Automated tests use a fake embedding backend instead, per the task's own testing spec ("fake embedding backend returning fixed-dimension vectors").

**Open issues / known gaps:**
- Manual verification steps (§8 "Manual Verification": real Ollama + real synthetic SOP + inspect `data/chroma/`) still need to be run by whoever has Ollama running locally.
- `backend/repositories/knowledge_base.py:64,214` has a pre-existing style oddity (`import sqlite3` at module bottom, referenced earlier in `create_kb_document`) — works correctly (Python resolves module globals at call time, and the import executes at module load before any function is called) but is confusing to read. Left untouched — it's Task 3's file, functionally correct, and not part of this task's required changes.
- No dedup, no reranking, no semantic chunking, no auto-retrieve path were introduced — confirmed against the Out-of-Scope list.

**Decisions made:**
- `category` is stored in Chroma metadata as `""` (empty string) when not provided, never `None` — `chromadb` 1.5.9 raises `InvalidArgumentError`/type-conversion error on `None` metadata values. Task 12.b's retrieval code must treat `""` as "no category", not `None`.
- One process-wide `chromadb.PersistentClient`, lazily created and cached (`get_chroma_client()`), per §10 "Known Risks" ("avoid opening many clients against the same path"). `reset_chroma_client()` exists solely for test isolation (tests point `chroma_dir()` at a temp dir per test).
- PDF parsing uses `pypdfium2`'s `page.get_textpage().get_text_range()` (already a project dependency, used by `document_processing/ocr.py` for page-image rendering) rather than adding a new PDF library — text-layer extraction only, all pages concatenated, no page-count cap (per the task's resolved open question).
- Ingestion failure diagnosis is exclusively via the `error` audit event (`job_id=None`, `component="rag_ingestion"`, `context.kb_document_id`) — no new DB field, per the task's locked decision. `GET /api/v1/knowledge-base` continues to expose only `status`.

**Supersedes / references:** None (first entry for this log).

---

### Entry 2 — 2026-09-11 14:45 — Fixed audit `emit()` to allow `job_id=None` for `error` events

**What changed:** `backend/domain/audit/events.py:84-98` — `_validate_job_id()` previously allowed `job_id=None` **only** for `event_type == "network_check"`; every other event type (including `error`) raised `ValueError(f"Event type '{event_type}' requires a job_id")`. Added `_JOB_INDEPENDENT_EVENT_TYPES = frozenset({"network_check", "error"})` and updated the branch so `error` may also carry `job_id=None`. Also updated the docstrings on `_validate_job_id()` and `emit()` to describe the new behavior.

**Why:** `docs/audit.md:22` already documents this as intended ("`job_id` is null only for Job-independent events — for example `network_check` ... and an `error` event fired by a Job-independent background process such as knowledge-base ingestion"), and `tasks/12a-rag-ingestion.md` §6 "Audit / Events" locks this exact behavior for ingestion failures. The code (`_validate_job_id`) had not been updated to match the doc — this task's `_fail_ingestion()` needs `emit("error", "rag_ingestion", {...}, job_id=None)` to actually succeed. This file is not in the task's "Allowed Files" or "May Modify If Required" lists, but the change is a narrow, doc-anchored bugfix required to satisfy a rule the task spec explicitly locks (not a new architectural decision) — flagging here per `AGENTS.md` §4.6 rather than silently expanding scope elsewhere.

**How to verify:**
```bash
cd backend && .venv/bin/python -m pytest tests/test_audit_events.py tests/test_repositories_audit_events.py -q
```
33 passed — including `test_emit_non_network_check_without_job_id_raises` (uses `job_created`, still correctly rejected) and `test_emit_network_check_with_job_id_raises` (unaffected). No existing test asserted `error` requires a `job_id`, so nothing needed updating for the new behavior itself; `tests/test_rag_ingestion.py::TestFailureHandling` exercises the new path end-to-end (unparseable file and embedding-failure tests both depend on this emit succeeding).

**Open issues / known gaps:** None — this brings the code in line with the already-published doc.

**Decisions made:** `error` joins `network_check` as the only two event types where `job_id=None` is valid; every other type in `VALID_EVENT_TYPES` still requires a `job_id`. Did not add a broader "job-independent" flag to the event-type table — kept the change minimal (a frozenset check), matching the existing code's style.

**Supersedes / references:** Builds on Entry 1 (this fix was required to make `_fail_ingestion()` in Entry 1's `ingestion.py` work).

---

### Entry 3 — 2026-09-11 14:50 — Investigated pre-existing test failures (not regressions)

**What changed:** No code change — investigation only, recorded here so the next session doesn't re-investigate.

**Why:** Full-suite run (`cd backend && .venv/bin/python -m pytest -q`, excluding the 4 collection errors from missing `python-docx`/`openpyxl`/`PIL`/`psutil`, which are pre-existing gaps in this venv unrelated to this task) showed 6 failures in `tests/test_model_runtime.py`. Investigated each:
- 5 are `TestGenerateIntegration`/`TestEmbedIntegration` tests that call the real Ollama HTTP API and fail with `ModelRuntimeUnavailableError: Ollama unreachable` because no `ollama serve` is running in this sandboxed environment — expected, unrelated to this task's changes.
- `TestStaticCheck::test_only_runtime_imports_httpx_for_model` fails because it scans `backend_root.rglob("*.py")` for Ollama-endpoint patterns and only skips files whose path parts contain the literal string `"venv"` (`tests/test_model_runtime.py`'s own logic) — but this project's virtualenv directory is named `.venv` (leading dot), so `"venv" in py_file.parts` never matches and the whole `.venv/` tree gets scanned. Confirmed via `git stash` that this test **already failed before any change in this session** (it matched `.venv/lib/.../pygments/unistring.py` and `.venv/lib/.../pip/_vendor/pygments/unistring.py`, both pre-existing in the venv from `pip` itself, and `.venv/lib/.../opentelemetry/semconv/.../gen_ai_attributes.py`). Adding `chromadb` (Entry 1) added one more incidental match (`chromadb/utils/embedding_functions/ollama_embedding_function.py`, an unused optional integration bundled with the library) but did not introduce the underlying bug.

**How to verify:** `cd backend && git stash && .venv/bin/python -m pytest -q tests/test_model_runtime.py::TestStaticCheck && git stash pop` reproduces the pre-existing failure without any of this session's changes applied.

**Open issues / known gaps:** ~~`tests/test_model_runtime.py`'s venv-skip check should be `".venv" in py_file.parts or "venv" in py_file.parts`~~ — fixed in Entry 4 below, at the user's explicit request.

**Decisions made:** Initially left `tests/test_model_runtime.py` untouched (not this task's file) — superseded by Entry 4.

**Supersedes / references:** Superseded by Entry 4.

---

### Entry 4 — 2026-09-11 15:10 — Fixed `test_model_runtime.py` venv-skip bug (user request)

**What changed:** `backend/tests/test_model_runtime.py:369` — `TestStaticCheck::test_only_runtime_imports_httpx_for_model`'s skip check `if "venv" in py_file.parts:` (exact-equality membership test against path components) never matched this project's virtualenv directory, named `.venv` (leading dot), so the whole `.venv/` tree was scanned for Ollama-endpoint patterns. Changed to `if any("venv" in part for part in py_file.parts):` — a substring check per path component, matching `.venv`, `venv`, or any similarly named directory.

**Why:** User explicitly asked to fix the pre-existing bug identified in Entry 3, with instructions to keep the change minimal. This is a one-line, single-file fix with no behavioral effect outside the test itself.

**How to verify:**
```bash
cd backend && .venv/bin/python -m pytest tests/test_model_runtime.py::TestStaticCheck -q
# 2 passed
.venv/bin/python -m pytest -q --ignore=tests/test_artifacts_docx.py --ignore=tests/test_artifacts_xlsx.py \
  --ignore=tests/test_document_processing.py --ignore=tests/test_lifecycle_manager.py -m "not integration"
# 326 passed, 9 skipped, 5 deselected (Ollama-integration tests)
```

**Open issues / known gaps:** None — the 4 remaining pre-existing collection errors (`python-docx`/`openpyxl`/`PIL`/`psutil` not installed in this venv) and the 5 Ollama-integration tests are unrelated environment gaps, not code bugs; out of scope for this fix.

**Decisions made:** Used `any(... for part in py_file.parts)` rather than adding `.venv` as a second literal alongside `venv`, so any differently-named virtualenv directory (`env`, `.env`, etc. — anything containing "venv" as a substring) is still caught; scoped strictly to this one test file since that's all the bug touched.

**Supersedes / references:** Resolves the gap flagged in Entry 3.

---

### Entry 5 — 2026-09-11 15:00 — branch complete (Task 12.a)

**Status:** completed (Task 12.a only — this log's `Status:` line covers the whole `rag` workstream and stays `in-progress` until Task 12.b lands)

**Summary:** Implemented the full KB ingestion pipeline (`domain/rag/ingestion.py`) and KB management API (`api/knowledge_base.py`, registered in `main.py`), added `chromadb` to `requirements.txt`, fixed a doc/code mismatch in `domain/audit/events.py` required for the locked `error`-event failure-reporting decision, fixed an unrelated pre-existing `.venv`-skip bug in `test_model_runtime.py` (Entry 4, user-requested), and wrote `tests/test_rag_ingestion.py` (11 tests, all passing). No locked contract (`AGENTS.md` §6) was violated; no new capability, event type, or DB field was introduced. Task 12.b (retrieval + `search_knowledge_base` executor) is unstarted — the Chroma collection name and chunk-metadata field list are frozen above for whoever picks it up.

**Final test status:**
```
tests/test_rag_ingestion.py: 11 passed
Full suite (excluding pre-existing missing-dependency collection errors from python-docx/openpyxl/PIL/psutil
not installed in this venv): 326 passed, 9 skipped, 5 deselected (-m "not integration", require live Ollama)
```

**Reviewer notes:**
- `backend/domain/audit/events.py` is touched outside this task's nominal file list — see Entry 2 for the justification (doc-anchored, minimal, required by this task's own locked decision).
- `backend/tests/test_model_runtime.py` is also touched outside this task's file list — a one-line bugfix (Entry 4) done at the user's explicit request, unrelated to RAG.
- Manual verification (§8, real Ollama + real Chroma inspection) has not been run — no Ollama available in this session's sandbox. Please run it before merge if possible: `ollama serve` with `qwen3-embedding:0.6b` pulled, `POST` a real synthetic SOP, poll `GET /api/v1/knowledge-base` until `ready`, inspect `data/chroma/`, then `DELETE` and confirm removal.
- `chromadb==1.5.9` was installed into `backend/.venv`; whoever provisions a fresh environment should re-run `pip install -r backend/requirements.txt`.

## Open questions for the user

None outstanding — the two "Resolved" items in the task spec (§11) were followed as locked decisions, and no new ambiguity was hit that isn't already covered by Entries 1–3 above.

## Links
- PR: (not yet opened — human developer step per `AGENTS.md` §7)
- Related branches / logs: `feature/rag-ingestion`; Task 12.b will likely continue on this same branch or a follow-up `feature/rag-retrieval` branch and should read this log first.
- Doc references: `docs/rag.md`, `docs/api.md`, `docs/data-model.md`, `docs/audit.md`, `docs/models.md`, `docs/backend.md`, `docs/decisions.md` (ADR-03), `tasks/12a-rag-ingestion.md`
