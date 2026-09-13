# Full-Stack Test Plan — Backend API + Frontend UI

> The complete manual test pass for Bulwark, covering all four SIH demo
> workflows through **both surfaces**: the raw HTTP API (Postman/curl) and the
> React frontend. Companion to `README.md` (asset corpus) and
> `api_testing/README.md` (Postman kit). Every step is tagged:
>
> | Tag | Meaning |
> |---|---|
> | **[API]** | Postman / curl against `http://127.0.0.1:8000/api/v1` only |
> | **[UI]** | Frontend at `http://localhost:5173` only |
> | **[BOTH]** | Do it on the API, then confirm the same behavior in the UI (or vice versa) |

---

## 1. How to run the stack

Prerequisites, once:

1. **Ollama** running (menu-bar app or `ollama serve`), with the models from
   `config/resources.yaml` pulled: `qwen3.5:9b`, `qwen2.5-coder:7b`,
   `qwen3-embedding:0.6b`.
2. **Docker Desktop** running with the sandbox image built (only needed for
   Workflow B / Phase 5):
   `docker build -t bulwark-sandbox:latest sandbox/`
3. **PaddleOCR model pre-warm** on a cold machine (one-time, ~1 min; avoids a
   first-run download racing the 60s OCR pass timeout):
   ```bash
   backend/.venv/bin/python -c "from paddleocr import PaddleOCR; PaddleOCR(lang='en', use_textline_orientation=True)"
   ```

Run the two servers (two terminals, from the repo root):

```bash
# Terminal 1 — backend (port 8000)
backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (port 5173, proxies to the backend)
cd frontend && npm run dev
```

Smoke check before anything else:

```bash
./api_testing/smoke_test.sh          # backend reachable, routes respond
curl -s http://127.0.0.1:11434/api/ps # Ollama reachable (shows loaded models)
```

Postman setup: import `api_testing/bulwark-postman-collection.json` +
`bulwark-postman-environment.json`, select the **Bulwark Local** environment.
The two multipart requests ship with an empty file field — pick the file
manually on first run.

---

## 2. Phase order

### Phase 0 — Environment & baseline **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 0.1 | **Health Check** | [API] Postman → Health & Network | `database` / `model_runtime` / `docker` all `ok` |
| 0.2 | **Network Status** | [API] | `external_connections_detected: false` — record baseline |
| 0.3 | **Connection indicator** | [UI] | StatusBar (bottom): "Local backend connected" green dot; **not** simulation mode (Workbench must not show the SIM fallback banner) |
| 0.4 | **Ollama visibility** | [API] | `curl 127.0.0.1:11434/api/ps` — see §4 "Model visibility" for what the app itself does/doesn't show |

> **Workflow D standing rule:** re-run 0.2 after every phase; it must never
> flip. In the UI, the sovereignty indicator (StatusBar) must stay healthy
> green the whole session.

### Phase 1 — Knowledge base seeding **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 1.1 | **List KB** | [API] | Delete any stale/`failed` rows from earlier sessions |
| 1.2 | **Ingest KB ×4** | [API] | `test-assets/knowledge-base/SOP-001..004-*.md`, metadata `{"title": "SOP-00X-…", "category": "sop"}` → `202` |
| 1.3 | **Poll readiness** | [API] | All 4 → `status: "ready"`, `chunk_count > 0` (`202` ≠ ready) |
| 1.4 | **Knowledge page** | [UI] | Navigate to Knowledge — all 4 SOPs listed with titles and status |
| 1.5 | **Sovereignty during ingestion** | [UI] | Indicator stays green (embedding calls are local Ollama only) |

### Phase 2 — Conversations & first contact **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 2.1 | **Create/Get Conversation** | [API] | 201 + row exists, empty messages; bogus-id GETs → 404 envelope (check the error shape once) |
| 2.2 | **First message via UI** | [UI] | Type any direct question in the chat (e.g. "What is 2+2?") → conversation created, message bubbles render **with real times** (not "Invalid Date") |
| 2.3 | **Get Conversation reflects it** | [API] | The UI-created conversation + user message visible via API (roles/content/timestamps) |

### Phase 3 — Workflow C: grounded RAG **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 3.1 | **Grounded question (Postman)** | [API] | Demo Workflows → Workflow C, but with a **covered** question from `test-assets/prompts/rag-test-questions.md` §A (e.g. pump vibration bands). Trace: exactly **one** `search_knowledge_base` (identical-proposal guard), explicit `tool_invoked`, answer cites the SOP's actual numbers |
| 3.2 | **Grounded question (UI)** | [UI] | Same question in the chat → JobTracePanel streams events **live via SSE** (no freeze); RagEvidencePanel shows the retrieved chunks; answer grounded |
| 3.3 | **No-duplication check** | [UI] | Refresh mid-job or after completion → no doubled events in the trace (event_id dedupe) |
| 3.4 | **Not-covered (C2)** | [BOTH] | The pre-filled extinguisher question: **one** search → honest "not in the KB" answer; no loop, no truncation in the Ollama log. Run once via Postman, once via UI |
| 3.5 | **Cross-SOP confusion (B1–B4)** | [API] | `rag-test-questions.md` §B — retrieval must not conflate pump-seal classes with valve-leak grades |
| 3.6 | **Section D not-covered set** | [API] | All honest no-grounding (`results: []` at the 0.50 floor; no fabrication) |
| 3.7 | **Multi-turn (E1–E4)** | [API] | Same conversation, C3 retrieval-judgment cases |
| 3.8 | **Sovereignty during RAG** | [UI] | Indicator green throughout (embedding + Chroma are local) |

### Phase 4 — Workflow A: scan → findings → approval note (.docx) **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 4.1 | **Upload clean report** | [API] | `test-assets/documents/inspection-report-clean.png` → `documentId`; Get Document Metadata confirms |
| 4.2 | **Run Workflow A (Postman)** | [API] | Trace: `extract_document` (~15s, no errors) → `search_knowledge_base` → `create_docx` → `artifact_created`; `artifact_ids[]` populated |
| 4.3 | **Download & judge artifact** | [API] | Copy id from `artifact_ids[]` → Get Artifact Metadata + Download (binary = the .docx itself, save to file). Verify against ground truth (README §4): 8.3 mm/s → SOP-001 Band 3, 7 days, notify Area Engineer; ~6 drops/min → Class II; temps Normal |
| 4.4 | **Same via UI** | [UI] | Upload the PNG via UploadButton → submit the Workflow A prompt → trace streams live → ArtifactPanel lists the .docx with real size/date → download from the UI opens it |
| 4.5 | **Attachment note visible** | [UI] | The user bubble shows the `[Attached document(s): …]` note (known cosmetic gap — flagged for the frontend owner) |
| 4.6 | **Model attribution in trace** | [BOTH] | Trace shows `model_invoked` with `qwen3.5:9b` (reasoning + vision-if-escalated); see §4 Model visibility |

### Phase 5 — Workflow B: generate_code → execute_code (sandbox) **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 5.1 | **B1 via UI** | [UI] | Submit a B1 coding task from `test-assets/prompts/coding-test-prompts.md` → trace shows `generate_code` **with `qwen2.5-coder:7b` in the model_invoked events** → `execute_code` → stdout with the hand-computed output |
| 5.2 | **B1–B2 via Postman** | [API] | Same tasks; deterministic outputs match the file's expected values |
| 5.3 | **B3 correction loop** | [BOTH] | Deliberate first-attempt bug → correction → a **second, distinct** `execute_code` step (legal under the identical-proposal guard) |
| 5.4 | **B4a/B4b sandbox security** | [BOTH] | Network-install attempts fail **honestly** inside `--network none` — never fabricated success; UI shows the failed execution as a failure, not a fake pass |
| 5.5 | **Docker prerequisites** | [API] | If `docker_unavailable` appears: Docker Desktop running + `bulwark-sandbox:latest` built (see §1) |

### Phase 6 — Upload-boundary & extraction failure paths **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 6.1 | **Unsupported .docx → documents** | [API] | `test-assets/documents/unsupported-document.docx` → `400 INVALID_MIME_TYPE` |
| 6.2 | **Unsupported .docx → KB ingest** | [API] | Same file via `POST /knowledge-base/documents` → `400 INVALID_MIME_TYPE` (two independent allowlists) |
| 6.3 | **Oversized file** | [API] | `oversized-test-file.bin` with explicit `Content-Type: image/png` → `400 FILE_TOO_LARGE` (`max_size_bytes: 10485760`). MIME is checked **before** size — wrong Content-Type → wrong error |
| 6.4 | **UI shows the rejections** | [UI] | Trigger 6.1 via UploadButton → ErrorBanner surfaces the API error with message (code header may show "ERROR" — known cosmetic gap) |
| 6.5 | **Corrupt image** | [BOTH] | `corrupt-document.png` uploads **succeeds** (only header/size validated) → job on it → `extract_document` returns `failed` (`UnreadableDocumentError`) — no crash, no silent empty success; UI trace shows the failure honestly |

### Phase 7 — Degraded input & OCR escalation **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 7.1 | **Degraded report via UI** | [UI] | Upload `inspection-report-degraded.png`, run Workflow A → warnings on reduced confidence; **91 °C Critical finding must survive** (never softened/dropped) |
| 7.2 | **Escalation signals** | [API] | Check `data/extraction/{document_id}.json` `signals` before calling escalation a bug — this PaddleOCR build may not populate layout labels (corpus README §15); confidence/completeness carry escalation |
| 7.3 | **Vision attribution** | [BOTH] | If escalation fires: trace shows `model_invoked` on the `vision` resource |

### Phase 8 — Capability-selection battery **[API]** (spot-check **[UI]**)

| # | Test | Surface | Expect |
|---|---|---|---|
| 8.1 | **24-prompt battery** | [API] | All prompts from `test-assets/prompts/capability-selection-battery.md`: OCR→`extract_document`, code→`generate_code`, retrieval→`search_knowledge_base`, #13–20 direct → plain `respond` with **no** capability, #21–24 → one search + honest no-grounding |
| 8.2 | **UI spot-checks** | [UI] | Run 2–3 prompts of different categories in the chat; each trace must match its category |

### Phase 9 — SSE, destructive endpoints & cleanup **[BOTH]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 9.1 | **SSE raw stream** | [API] | `curl -N localhost:8000/api/v1/jobs/{id}/events` during a fresh job — full event stream incl. any mid-job `error` events, closing only on `job_completed` |
| 9.2 | **SSE late-join** | [BOTH] | Open the UI trace mid-job (or refresh): replayed history + live tail, **no duplicates**, stream survives mid-job `error` events |
| 9.3 | **Delete KB document** | [API] | Delete one SOP → gone from List → 404 on re-delete → re-ingest to restore |
| 9.4 | **UI reflects deletion** | [UI] | Knowledge page updates after delete/restore |

### Phase 10 — Model visibility (informational) **[API]**

| # | Test | Surface | Expect |
|---|---|---|---|
| 10.1 | **Which model served which step** | [BOTH] | Every `model_invoked` in the trace shows `model_identifier` + `resource_type` (UI renders it in the capability activity feed) |
| 10.2 | **Loaded-models check** | [API] | `curl 127.0.0.1:11434/api/ps` — the only way to see what's currently resident. The **app has no live "loaded models" indicator** (no endpoint exposes Ollama's /api/ps state; `/health` is a reachability probe only). Enhancement idea: a `GET /api/v1/model-status` + StatusBar indicator — needs a docs/api.md decision first |
| 10.3 | **Load/unload audit trail** | [API] | `resource_loaded`/`resource_unloaded` events in the DB/audit stream show lifecycle transitions per model |

---

## 3. Standing rules (every phase)

- **Workflow D:** Network Status re-check after every phase (API); sovereignty
  indicator green throughout (UI). Never flips.
- **One fresh conversation per workflow demo** — conversation history biases
  the model (observed: it surrendered based on stale failure history).
- **Postman gotchas:** multipart file fields empty on first import; `artifactId`
  never auto-captures (copy from `artifact_ids[]`); check Test Results if an
  id-capture script silently failed.
- **Ollama log hygiene:** no `truncating input prompt` warnings, no 2-minute
  generations. If seen, something regressed.
- **Frontend failure honesty:** failed steps/executions must render as
  failures — never as fabricated successes.

## 4. Model visibility — what exists today

| Question | Answer |
|---|---|
| Which model served a step? | Trace `model_invoked` events (`model_identifier` + `resource_type`) — UI capability-activity feed renders them during/after a job |
| Which models are **currently loaded**? | **Not visible in the app.** No endpoint exposes Ollama's load state; `/health` only probes reachability. Check `curl 127.0.0.1:11434/api/ps` manually |
| Load/unload history? | `resource_loaded` / `resource_unloaded` audit events (DB + trace) |
| Gap (flagged, not built) | A live model-load indicator (endpoint + StatusBar chip) needs a `docs/api.md` contract decision before implementation |

## 5. Known cosmetic gaps (flagged for the frontend owner)

- `ApiError` has no `code` → ErrorBanner header shows literal "ERROR"
- `[Attached document(s): …]` note renders raw in user bubbles
- Workbench page-level `handleError`/`ErrorBanner` is dead code (ChatPanel's
  own error path works)
- `services/api.js` `BASE_URL` hardcoded (no env override — fine on the
  demo machine's default port)

## 6. Asset cross-reference

See `test-assets/README.md` for the full corpus, ground truths (§4–§5), the
SOP fact map (§6), and the implementation-specific caveats (§15). Prompt
scripts: `test-assets/prompts/*.md`.
