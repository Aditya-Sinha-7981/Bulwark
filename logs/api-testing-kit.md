# logs/api-testing-kit.md

> Feature / workstream: `api-testing-kit`  (branches: `testing/backend_api`)
> Started: 2026-09-11 by claude-sonnet-5
> Status: completed

## Goal

Give the project owner (Aditya, backend/integration lane) a way to manually
exercise the real, no-stub backend (Task 15 — `docs/api.md` surface, Job
Manager → Policy → Executor dispatch loop) before frontend integration
(Task 17) exists. Scope: a code-verified API reference doc plus an
importable HTTP-client collection covering every registered route and the
four `docs/demo.md` workflows. No application code touched.

## Plan

1. Read `AGENTS.md`, `members/aditya.md`, `tasks/15-backend-api-integration.md`,
   `logs/feature-backend-integration.md`, `docs/demo.md` to understand what's
   actually implemented vs. still-stubbed, and what the four demo workflows
   require.
2. Inspect the repo directly (routers, `config/*.yaml`, `sandbox/Dockerfile`)
   rather than trusting `docs/api.md` alone — confirm which capability
   executors are real (all of them, per `git log`: RAG, sandbox, OCR, docx/xlsx
   all merged onto `main` by this point) and which routers are registered in
   `backend/main.py`.
3. Write `docs/api-manual-testing-guide.md` — a per-endpoint practical
   companion to `docs/api.md`, with exact request/response shapes, validation
   rules, and error codes read from the actual router source, not just the
   design doc.
4. Build an importable collection (`api_testing/`) covering every route plus
   pre-filled Workflow A/B/C job bodies, environment variables for id
   chaining, a CLI smoke-test script, and fixture assets (synthetic SOP text
   + a generated scanned-report image) since none existed in the repo yet.
5. User switched HTTP-client tooling mid-session (Thunder Client → Postman
   VS Code extension) — rebuilt the collection/environment for Postman's
   v2.1 schema and updated both docs to match.
6. Log, then commit directly (user explicitly authorized committing on this
   branch for this session, with no AI attribution in the commit message).

## Entries

### Entry 1 — 2026-09-11 — `docs/api-manual-testing-guide.md`

**What changed:** New file, `docs/api-manual-testing-guide.md`. Documents
every endpoint actually registered in `backend/main.py`
(`conversations`, `jobs`, `documents`, `artifacts`, `knowledge_base`,
`health`, `network_status`) with request/response shapes, curl examples, and
validation detail read directly from each router
(`backend/api/documents.py::_validate_upload` MIME allowlist + size limit,
`backend/api/knowledge_base.py` allowed extensions, `backend/api/health.py`
probe mechanics, `backend/api/artifacts.py`'s `storage_path`-based download
resolution).

**Why:** `docs/api.md` is the design-level contract but omits operational
detail (exact MIME allowlists, size limits, per-router error codes) needed to
actually drive the API by hand. `AGENTS.md` §3's "code is the source of
truth" applies here — several details in this guide are not in `docs/api.md`
at all.

**How to verify:** Diff the guide's per-endpoint claims against
`backend/api/*.py` — every rule cited (MIME allowlist, `EMPTY_FILE`/
`FILE_TOO_LARGE`/`INVALID_MIME_TYPE`/`INVALID_METADATA` codes, the
`storage_path` vs. `artifact_id` download-resolution workaround) has a direct
source-line origin, listed in the guide's "Known gaps / gotchas" section.

**Open issues / known gaps:**
- No KB-seeding script or demo fixtures existed anywhere in the repo at
  research time — flagged in the guide; later addressed for this workstream
  by the fixtures in `api_testing/fixtures/` (Entry 2) and independently, more
  extensively, by the separate `test-assets/` corpus (`logs/test-assets.md`,
  committed after this entry).
- `documents` router's 404 uses code `DOCUMENT_NOT_FOUND` while
  `conversations`/`artifacts`/`jobs` use the generic `not_found` — same
  envelope shape, different `code` string per router; noted so a caller
  doesn't hardcode one error code across all resources.

**Decisions made:** None architectural — pure documentation, no contract
change.

**Supersedes / references:** None (first entry).

---

### Entry 2 — 2026-09-11 — `api_testing/` Thunder Client kit (superseded by Entry 3)

**What changed:** Created `api_testing/` with `bulwark-thunder-collection.json`
(7 folders / 18 requests: Conversations, Jobs, Documents, Artifacts,
Knowledge Base, Health & Network, and pre-filled Workflow A/B/C job bodies
matching `docs/demo.md`), `bulwark-thunder-environment.json`, a CLI
`smoke_test.sh` (health + network-status + create-conversation + list-KB),
and `fixtures/` — two synthetic SOP `.txt` files
(`sop-fire-safety.txt`, `sop-equipment-maintenance.txt`) to seed the
knowledge base with, and `generate_scan_image.py` (Pillow-based — renders a
synthetic "scanned inspection report" PNG plus a deliberately
blurred/rotated/noisy degraded variant), since no real scan/demo asset
existed in the repo. `api_testing/README.md` documents import steps and a
numbered run order across all four demo workflows.

**Why:** Requested by the user directly, as the practical counterpart to
Entry 1's reference doc — something to actually click through rather than
hand-type every curl call.

**How to verify:** `python3 -c "import json; json.load(open('api_testing/bulwark-thunder-collection.json'))"` (validated at the time — file no longer
present, see Entry 3).

**Open issues / known gaps:** The Thunder Client "Tests" auto-variable-capture
blocks (`type: set-env-var`) were hand-written against Thunder Client's
documented schema, not exported from a live instance — flagged in the README
as needing verification after import, since the extension's internal test
format is not fully public and varies by version.

**Decisions made:** Built `api_testing/` as a separate, narrower kit rather
than extending `docs/` — matches the existing project convention of `docs/`
being for design contracts, not operational tooling.

**Supersedes / references:** Entry 1 (this is the tooling counterpart to that
reference doc).

---

### Entry 3 — 2026-09-11 — Rebuilt `api_testing/` for the Postman VS Code extension

**What changed:** User switched HTTP-client tooling mid-session. Removed
`bulwark-thunder-collection.json` / `bulwark-thunder-environment.json`;
added `bulwark-postman-collection.json` (Postman Collection v2.1 schema,
same 7 folders / 18 requests) and `bulwark-postman-environment.json`.
Id-chaining now uses standard Postman `pm.environment.set(...)` "Tests"
scripts instead of the Thunder-Client-specific format from Entry 2 — this is
publicly documented Postman syntax, so it is more reliably correct than the
prior hand-guessed schema. Updated `api_testing/README.md` (import steps,
run order, known limitations) and `docs/api-manual-testing-guide.md`
(title, SSE note, multipart-body note, "Suggested Postman collection layout"
section, cross-link to `api_testing/`) to match. Fixture files
(`sop-*.txt`, `generate_scan_image.py`, `smoke_test.sh`) were untouched —
not tool-specific.

**Why:** Direct user request after installing the Postman VS Code extension
instead of continuing with Thunder Client.

**How to verify:**
```
python3 -c "import json; json.load(open('api_testing/bulwark-postman-collection.json')); json.load(open('api_testing/bulwark-postman-environment.json'))"
# both valid JSON (confirmed this session)
grep -rn "Thunder Client" docs/api-manual-testing-guide.md api_testing/README.md
# no remaining references (confirmed this session)
```
Import `api_testing/bulwark-postman-collection.json` and
`bulwark-postman-environment.json` into the Postman VS Code extension; run
"Health Check" first per the README's suggested run order.

**Open issues / known gaps:**
- The two multipart requests (`Upload Document`, `Ingest KB Document`) ship
  with an empty `file` field — a Postman collection export cannot embed a
  portable local file path, so the field must be set manually (browse to the
  fixture) the first time each request runs on a given checkout.
- SSE (`Jobs → Stream Job Events`) may not render cleanly inside the Postman
  VS Code extension; `curl -N` remains the documented fallback in both docs.
- This kit's `fixtures/` (2 SOPs + 1 scan-image generator) is narrower than
  the independently-built `test-assets/` corpus (4 SOPs, clean+degraded
  report images, upload-failure fixtures, prompt scripts — see
  `logs/test-assets.md`), which landed on this same branch after this
  workstream's Entry 2. The two are not merged/reconciled — `api_testing/`
  stays the quick-smoke-test kit, `test-assets/` is the deeper corpus; both
  READMEs cross-reference each other's existence but do not depend on one
  another.

**Decisions made:** Kept `api_testing/` as the lightweight kit rather than
folding it into or replacing `test-assets/` — they serve different purposes
(quick per-endpoint HTTP-client smoke test vs. deep SOP/demo-asset corpus for
full workflow runs), consistent with the boundary `test-assets/README.md`
already documents from its side.

**Supersedes / references:** Supersedes Entry 2's Thunder Client files
(deleted, not kept for reference — the git history retains them if ever
needed). References Entry 1 (the doc these files exercise).

---

## Open questions for the user

None outstanding.

## Links

- Related: `logs/test-assets.md` (the separate, deeper synthetic-asset-corpus
  workstream on this same branch — do not conflate the two; see Entry 3's
  note), `api_testing/README.md`, `docs/api-manual-testing-guide.md`.
- Doc references: `docs/api.md`, `docs/demo.md`, `docs/testing.md`,
  `tasks/15-backend-api-integration.md`, `AGENTS.md` §4 (work-log rules),
  §4.2 ("owned by the feature/workstream owner").
