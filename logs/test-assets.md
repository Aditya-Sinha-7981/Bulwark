# logs/test-assets.md

> Feature / workstream: `test-assets`  (branches: `testing/backend_api`)
> Started: 2026-09-12 by claude-sonnet-5
> Status: completed

## Goal

Prepare a complete, synthetic test/demo asset corpus (`test-assets/`) so the
four SIH demo workflows (`docs/demo.md`) and their documented failure paths
(`docs/testing.md` "Failure injection") can be exercised manually, end to
end, without any real organizational data. Asset preparation only — no
application code, API contract, capability, schema, or architecture change
in scope, per explicit user instruction.

## Plan

1. Read `AGENTS.md` + every doc listed in the task (`project-context.md`,
   `requirements.md`, `architecture.md`, `capabilities.md`, `demo.md`,
   `testing.md`, `rag.md`, `document-processing.md`, `artifacts.md`,
   `api.md`, `security.md`, `configuration.md`, `deployment.md`,
   `models.md`).
2. Inspect the actual backend implementation where a doc's claim needed
   code-level verification (upload validation, OCR pipeline, sandbox image,
   retrieval relevance floor) — code is authoritative over docs per
   `AGENTS.md` §3.
3. Check for an existing fixtures convention before creating a new one
   (found `api_testing/fixtures/` — a smaller, Postman-oriented kit; decided
   to leave it untouched and build the deeper `test-assets/` corpus
   alongside it, documented in `test-assets/README.md` §"purpose").
4. Author 4 cross-referenced synthetic SOPs, generate a clean + deliberately
   degraded inspection report image pair consistent with SOP-001, build the
   three upload-failure-path fixtures (corrupt PNG, unsupported DOCX,
   oversized `.bin`), and write the three prompt scripts (RAG, coding,
   capability-selection).
5. Write `test-assets/README.md` as the operator's manual, cross-checking
   every fact/threshold cited back to the actual SOP/report content.
6. Validate: confirm all files exist, DOCX opens, corrupt PNG actually fails
   to decode, oversized file exceeds the real configured limit (not just
   the documented default).
7. Commit (user explicitly authorized committing on this branch for this
   task, with no AI attribution in the commit message/trailer).

## Entries

### Entry 1 — 2026-09-12 01:00 — Doc + implementation research

**What changed:** No files yet — read every doc in the task list plus
`docs/agent.md`, `docs/sandbox.md`, `docs/api-manual-testing-guide.md`
(pre-existing, code-verified as of 2026-09-12 by a prior session). Inspected
`backend/api/documents.py`, `backend/api/knowledge_base.py`,
`backend/domain/document_processing/{pipeline,ocr}.py`,
`backend/domain/capabilities/extract_document.py`,
`backend/domain/sandbox/docker_executor.py`, `sandbox/Dockerfile`,
`backend/domain/rag/retrieval.py`, and `config/{capabilities,app,policy,resources}.yaml`.

**Why:** `AGENTS.md` §3 requires reading docs then inspecting the repo before
writing anything, specifically to avoid hallucinating capability names,
event types, or limits that drifted from the design docs.

**How to verify:** N/A (research entry).

**Open issues / known gaps:** None yet.

**Decisions made:**
- Use `test-assets/` per the task's explicit requested tree rather than
  extending `api_testing/fixtures/` in place — the two serve different
  purposes (quick Postman smoke test vs. deep manual/benchmark corpus);
  documented the relationship in `test-assets/README.md` §1 rather than
  silently picking one.
- `MAX_FILE_SIZE_BYTES` is exactly `10 * 1024 * 1024 = 10,485,760` bytes
  (`config/capabilities.yaml` → `extract_document.max_file_size_mb: 10`,
  read via `backend/api/documents.py`), not just "the documented ~10MB
  default" — the oversized fixture is sized against this exact number.
- `POST /api/v1/documents` checks MIME type **before** size
  (`backend/api/documents.py::_validate_upload`) — the oversized `.bin`
  fixture must be uploaded with an explicit allowed `Content-Type` or the
  size path never gets exercised. Documented explicitly in the README so a
  future tester doesn't misread a `400 INVALID_MIME_TYPE` as the wrong test
  result.
- `handwriting_detected`/`layout_complexity_flag` in
  `backend/domain/document_processing/ocr.py::_region_type_from_layout`
  depend on PaddleOCR's layout-classification labels being populated by the
  installed pipeline — not guaranteed. Decided to design the degraded report
  to reliably trigger escalation via `mean_ocr_confidence` and
  `completeness_estimate` instead (blur/noise/skew reduce confidence;
  handwritten text is sparser than printed text of the same content, so
  completeness estimate is directly affected too), and flagged this as an
  implementation-specific constraint in the README rather than assuming
  handwriting detection will fire.

**Supersedes / references:** None (first entry).

---

### Entry 2 — 2026-09-12 01:30 — Authored the 4-SOP knowledge-base corpus

**What changed:** Created `test-assets/knowledge-base/SOP-001-Pump-Maintenance.md`,
`SOP-002-Valve-Inspection.md`, `SOP-003-Pressure-Vessel-Inspection.md`,
`SOP-004-Workplace-Safety.md` — a fictional facility ("Trishul Thermal Power
Station"), fully synthetic, with exact numeric thresholds (vibration bands,
seal-leak classes, valve-leak grades, vessel thickness/pressure criteria,
PTW/LOTO timing) and deliberate cross-references between SOPs (SOP-001 §6 and
SOP-002 §5 both point to SOP-004 for LOTO mechanics; SOP-003 §2 points to
SOP-004 for vessel-entry isolation).

**Why:** `docs/rag.md` "Knowledge-base boundaries" requires genuinely
searchable synthetic content, not lorem-ipsum, and the task requires
questions with objectively verifiable answers plus deliberate cross-document
distinctions.

**How to verify:** Read the four files; cross-check the fact tables in
`test-assets/README.md` §6 against them; confirm no contradicting threshold
appears twice with different values.

**Open issues / known gaps:** None — content is final as authored.

**Decisions made:** Used strict/non-strict inequality boundaries consistently
(e.g. SOP-001 vibration: "≤4.5" Normal / ">4.5 and ≤7.1" Caution) so no
reading is ever ambiguous between two bands — this matters because the
inspection-report ground truth and the coding-prompt test data both rely on
values landing unambiguously in a specific band.

**Supersedes / references:** Entry 1.

---

### Entry 3 — 2026-09-12 02:00 — Generated clean + degraded inspection report images

**What changed:** Wrote a Pillow-based generator script (kept in the
session scratchpad, not committed — the two PNG outputs are the deliverable,
per the task's requested file list) and produced
`test-assets/documents/inspection-report-clean.png` and
`inspection-report-degraded.png`. Clean: printed form, high contrast, no
rotation, depicting pump CWP-204A with a Band-3/Alert vibration finding
(8.3 mm/s RMS) that maps directly to an explicit SOP-001 rule. Degraded: same
form template for a sister pump (CWP-204B), handwritten readings
(`Bradley Hand Bold` font) including a Critical bearing-temperature reading
(91°C), page rotated 2.3°, Gaussian-blurred, ~1.5% speckle noise, and a
blended low-contrast patch directly over the handwritten "Notes" lines.

**Why:** Task requires a clean OCR-should-succeed asset and a degraded asset
that exercises the documented OCR quality/escalation signals without being
unreadable.

**How to verify:** Open both PNGs (verified visually during this session);
cross-check `test-assets/README.md` §4/§5 ground-truth tables against the
rendered text — both were authored from the same script's literal string
values, so they cannot drift apart.

**Open issues / known gaps:** Two label/value overlaps were found and fixed
during visual review (label column width too narrow for "Mechanical Seal
Leakage:"/"Coupling Guard Condition:" on the clean report); the low-contrast
patch was initially placed over blank page space below the real content and
was repositioned to actually cover the handwritten Notes lines. Whether
escalation actually triggers on the degraded asset in a live run is flagged
in the README as unverifiable without running PaddleOCR (see Entry 1's
decision on this).

**Decisions made:** Used a sister-equipment-ID + later-date framing (CWP-204B,
one week after CWP-204A) rather than a duplicate of the same inspection, so
the degraded report is a distinct, independently-checkable Workflow A/C test
case rather than a noisy re-render of the clean one.

**Supersedes / references:** Entry 1 (implements the OCR-signal decision
made there).

---

### Entry 4 — 2026-09-12 02:20 — Built the three upload-failure fixtures

**What changed:** Created `test-assets/documents/corrupt-document.png` (valid
PNG signature + structurally-present but CRC-invalid/truncated IHDR chunk +
random bytes, no IDAT/IEND), `unsupported-document.docx` (valid DOCX via
`python-docx`, harmless placeholder text only), and `oversized-test-file.bin`
(10,600,000 bytes of generated filler — ~114KB over the real 10,485,760-byte
limit).

**Why:** `docs/testing.md` "Failure injection" requires testing OCR failure
(corrupt file), and the task requires upload-boundary rejection tests for an
unsupported MIME type and an oversized file, against the *actual* configured
limit rather than the documented default alone.

**How to verify:**
```
backend/.venv/bin/python3 -c "from PIL import Image; Image.open('test-assets/documents/corrupt-document.png').load()"
# -> raises PIL.UnidentifiedImageError (confirmed this session)
backend/.venv/bin/python3 -c "from docx import Document; Document('test-assets/documents/unsupported-document.docx')"
# -> opens cleanly, 3 paragraphs (confirmed this session)
ls -la test-assets/documents/oversized-test-file.bin   # 10600000 bytes
```

**Open issues / known gaps:** None.

**Decisions made:** Sized the oversized file at limit+~114KB rather than a
round number like 11MB or 15MB, per the task's "just large enough to cross
the actual limit... do not make it enormous" instruction.

**Supersedes / references:** Entry 1 (implements the size/MIME-order
decisions made there).

---

### Entry 5 — 2026-09-12 02:40 — Wrote the three prompt scripts and the README

**What changed:** Created `test-assets/prompts/rag-test-questions.md`
(Sections A–E mapped to `docs/testing.md`'s C1/C2/C3 cases, 8+4 covered
questions, 4 report+SOP combination questions, 6 deliberately-uncovered
questions, 4 multi-turn conversations), `coding-test-prompts.md` (B1–B4 per
`docs/testing.md` plus 3 additional deterministic industrial-calculation
tasks, all expected outputs hand-computed), `capability-selection-battery.md`
(24 prompts, 4 per category × 6 categories, margin above the ≥20 minimum),
and `test-assets/README.md` (the full operator's manual — 16 sections
covering purpose, inventory, workflow mapping, ground truth, failure
behavior, demo-critical vs. test-only split, ingestion order, and discovered
implementation constraints).

**Why:** Completes the requested corpus; the README is what makes the corpus
usable without re-deriving the SOP/report facts from scratch each time.

**How to verify:** Read `test-assets/README.md`; every numeric fact it cites
back to a SOP or report was checked against the source file during
authoring (Entry 2/3's content, not re-derived independently).

**Open issues / known gaps:** Three items explicitly flagged in the README
§16 as unverifiable without a live environment: (1) whether the degraded
report actually triggers vision escalation given the real installed
PaddleOCR build's layout-label support, (2) the real OCR confidence
PaddleOCR reports on the clean asset, (3) actual Chroma similarity scores for
the RAG questions against `qwen3-embedding:0.6b` relative to the 0.50
relevance floor. None of these block using the corpus — they're calibration
checks for whoever runs the live demo/benchmark.

**Decisions made:** No discrepancy between `docs/` and the actual
implementation was found that affects these assets (checked explicitly, per
`AGENTS.md`'s instruction to document rather than silently redesign around
one) — the one genuinely implementation-specific detail worth knowing
(PaddleOCR layout-label dependency for two of the four OCR quality signals)
is a testing caveat, not a docs/code contradiction.

**Supersedes / references:** Entries 1–4.

---

### Entry 6 — 2026-09-12 03:00 — Committed; workstream complete

**Status:** completed
**Summary:** 13 files added under `test-assets/` (README + 4 SOPs + 5
document fixtures + 3 prompt scripts). No application code, API contract,
capability, schema, or architecture doc was changed. Committed directly on
`testing/backend_api` per explicit user instruction for this task (including
an explicit instruction to omit the usual AI co-authorship trailer from the
commit message — noted here since it's a deviation from this repo's normal
attribution convention, scoped to this one commit by the user's own
direction, not a standing change to `git-workflow.md`).
**Final test status:** No automated test suite applies to this workstream
(asset preparation, not application code) — validation was manual, listed in
Entry 4/5 above and `test-assets/README.md` §16.
**Reviewer notes:** This entry itself was added late — the initial commit
(`fb2ca3f`, "Add synthetic test/demo asset corpus for SIH workflows") went in
*before* this log file existed, which is out of order relative to
`AGENTS.md` §5 step 11 ("append a log entry" before proposing the commit).
Caught when the user asked about it directly; logged here rather than
silently backdated, per the append-only rule (`AGENTS.md` §4.5) — the log
history should show what actually happened, including this gap, not a
tidied-up version of it.

---

### Entry 7 — 2026-09-12 21:09 — Full-stack test plan added (branch `docs/full-stack-test-plan`)

**What changed:** `test-assets/full-stack-test-plan.md` (new) — the complete
manual test pass covering all 9 backend phases from today's API session,
restructured to weave in frontend checks per phase, with every step tagged
**[API]** / **[UI]** / **[BOTH]**. Includes: how to run both servers (exact
commands, prerequisites incl. PP-OCR pre-warm), per-phase expectation tables,
standing rules (Workflow D network checks, fresh-conversation rule, Postman
gotchas), a Model-visibility section (what exists today: per-step
`model_invoked` attribution in traces; what doesn't: no live loaded-models
indicator — no endpoint exposes Ollama /api/ps; flagged as an enhancement
needing a `docs/api.md` decision), and the known frontend cosmetic gaps
handed to the frontend owner.

**Why:** The backend-API-only plan in `api_testing/README.md` predates the
frontend. After the frontend landed and the backend fixes were merged
(`1d3d35e`), the user asked for one consolidated plan covering both surfaces
in a defined order.

**How to verify:** File exists, references real fixtures/prompts by path, and
its expectations match the fixes from the 2026-09-12 session (see
`logs/feature-rag.md` Entry 8, `logs/feature-model-runtime.md` Entry 7,
`logs/feature-orchestrator.md` Entries 4–5, `logs/feature-job-system.md`
Entries 4–5, `logs/feature-ocr.md` Entries 6–8, `logs/feature-frontend-scaffold.md`
Entry 5). No application code changed.

**Open issues / known gaps:** The Phase 10 model-visibility enhancement is a
proposal only — needs user + `docs/api.md` decision before anyone builds it.

**Supersedes / references:** Extends Entry 6's corpus; complements (does not
replace) `api_testing/README.md`.

## Open questions for the user

None outstanding.

## Links

- Commit: `fb2ca3f` — "Add synthetic test/demo asset corpus for SIH workflows" (branch `testing/backend_api`)
- Related: `api_testing/README.md` (the pre-existing, narrower Postman fixture kit this corpus sits alongside), `docs/api-manual-testing-guide.md` (pre-existing, code-verified API reference used heavily during research)
- Doc references: `docs/project-context.md`, `docs/requirements.md`, `docs/architecture.md`, `docs/capabilities.md`, `docs/demo.md`, `docs/testing.md`, `docs/rag.md`, `docs/document-processing.md`, `docs/artifacts.md`, `docs/api.md`, `docs/security.md`, `docs/configuration.md`, `docs/deployment.md`, `docs/models.md`, `docs/agent.md`, `docs/sandbox.md`
