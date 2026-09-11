# api_testing/

Manual/local testing kit for the real backend (Task 15 integration, `main`
branch). No frontend yet, so this is how you exercise the four SIH workflows
end-to-end until Task 17. Companion reference: `docs/api-manual-testing-guide.md`
(full per-endpoint request/response/validation detail).

## Contents

- `bulwark-postman-collection.json` — importable Postman v2.1 collection: 7
  folders, 18 requests covering every registered route
  (conversations, jobs, documents, artifacts, knowledge-base, health,
  network-status) plus 3 pre-filled "Demo Workflows" requests matching
  `docs/demo.md` Workflows A/B/C.
- `bulwark-postman-environment.json` — a `Bulwark Local` environment with
  `baseUrl` pre-set to `http://127.0.0.1:8000/api/v1` and empty placeholders
  for `conversationId` / `jobId` / `documentId` / `artifactId` / `kbDocumentId`.
- `fixtures/sop-fire-safety.txt`, `fixtures/sop-equipment-maintenance.txt` —
  synthetic SOP text files to seed the knowledge base with (no seed script or
  fixtures existed anywhere in the repo before this).
- `fixtures/generate_scan_image.py` — renders a synthetic "scanned inspection
  report" PNG (`scan-clean.png` + a deliberately blurred/rotated/noisy
  `scan-degraded.png`) for Workflow A, since no real scan asset exists either.
- `smoke_test.sh` — a 30-second CLI check (health, network-status, create a
  conversation, list KB) to run before touching Postman at all.

## Setup (once dependencies are installed and the backend is running)

```bash
# from repo root
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# in another terminal:
./api_testing/smoke_test.sh
python3 api_testing/fixtures/generate_scan_image.py   # needs Pillow (comes with paddleocr)
```

## Importing into the Postman VS Code extension

1. Postman sidebar → **Collections** → **Import** → select
   `api_testing/bulwark-postman-collection.json`.
2. Postman sidebar → **Environments** → **Import** → select
   `api_testing/bulwark-postman-environment.json`, then pick **Bulwark Local**
   from the environment dropdown (top-right) so `{{baseUrl}}` and friends
   resolve.
3. Each id-producing request (Create Conversation, Create Job, Upload
   Document, Ingest KB Document, and the 3 Demo Workflow jobs) carries a
   **Tests** script (`pm.environment.set(...)`) that auto-populates
   `conversationId` / `jobId` / `documentId` / `kbDocumentId` after a
   successful response — standard Postman test-script syntax, so it should
   fire on import without edits. Check the **Test Results** tab on a response
   if a downstream request 404s; worst case, copy the id into the environment
   by hand.
4. `artifactId` has no producing request to auto-capture from — after a
   Workflow A/B job completes, copy a value out of **Get Job Status**'s
   `artifact_ids[]` into the environment manually before running
   **Artifacts → Get Artifact Metadata / Download Artifact**.

## Suggested run order

1. **Health & Network → Health Check** — confirm `database`/`model_runtime`/`docker` are all `ok` before doing anything else.
2. **Health & Network → Network Status** — note the baseline; re-run this throughout (Workflow D — it should never flip to `true`).
3. **Knowledge Base → Ingest KB Document** — run it twice, once per fixture file (`sop-fire-safety.txt`, `sop-equipment-maintenance.txt`). Poll **List KB Documents** until both show `status: "ready"`.
4. **Conversations → Create Conversation** — sets `{{conversationId}}`.
5. **Demo Workflows → Workflow C** — grounded KB question. Poll **Jobs → Get Job Status**, then **Get Job Trace** and confirm `search_knowledge_base` appears as an explicit `tool_invoked` step.
6. **Documents → Upload Document** — point it at `fixtures/scan-clean.png` (generate it first). Sets `{{documentId}}`.
7. **Demo Workflows → Workflow A** — uses `{{documentId}}` + the seeded KB. Check the trace shows `extract_document → search_knowledge_base → create_docx → artifact_created`, then **Artifacts → Get Artifact Metadata** / **Download Artifact** (copy the id from `Get Job Status`'s `artifact_ids[]` into `{{artifactId}}` first).
8. **Demo Workflows → Workflow B** — needs Docker running + `bulwark-sandbox:latest` built. Check the trace shows `generate_code` and `execute_code` as distinct steps.
9. Optional degraded-input pass: re-upload `scan-degraded.png` for Workflow A and confirm low-confidence findings are flagged honestly rather than fabricated.
10. Optional failure-path pass: disable a capability in `config/capabilities.yaml`, re-run any workflow using it, confirm the trace shows a `policy_decision: deny` and the capability never actually runs.

## Known limitations of this kit

- The SSE endpoint (`Jobs → Stream Job Events`) may not render well inside
  the Postman VS Code extension — `curl -N` is the reliable fallback
  (see `docs/api-manual-testing-guide.md` §2).
- The two multipart requests (`Upload Document`, `Ingest KB Document`) ship
  with an empty `file` field — Postman can't embed a portable local file path
  in an exported collection, so you must click into the field and select the
  fixture file yourself the first time you run each request in a new machine/checkout.
- Nothing here replaces `backend/tests/` (`pytest`) — this kit is for the
  no-stub, real end-to-end manual pass discussed for Task 15/19, not a
  substitute for automated tests.
