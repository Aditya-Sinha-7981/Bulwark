# test-assets/ — Bulwark Manual Test & Demo Corpus

Operator's manual for this directory. Synthetic, fictional content only — no
real organizational data (per `docs/rag.md` "Knowledge-base boundaries" and
`AGENTS.md` §6). Everything here describes a fictional facility, "Trishul
Thermal Power Station" (TTPS), and fictional people/equipment IDs.

This corpus is additive to `api_testing/` (the existing Postman/curl kit with
its own smaller `api_testing/fixtures/` — 2 SOP `.txt` files and an on-the-fly
scan-image generator). `api_testing/fixtures/` was left untouched: it exists
to make the Postman collection self-contained for a quick smoke test;
`test-assets/` is the deeper, deliberately-authored corpus for manually
exercising all four SIH demo workflows and their documented failure paths.
If you're doing a 30-second sanity check, use `api_testing/`; if you're doing
a real manual test pass (or SIH rehearsal), use this directory.

---

## 1. Purpose

A complete, internally-consistent set of synthetic documents and prompts
that let a human manually exercise:

- **Workflow A** (`docs/demo.md`) — scanned report → `extract_document` →
  `search_knowledge_base` → structured findings → `create_docx`.
- **Workflow B** — coding request → `generate_code` → `execute_code`,
  including the correction-loop and sandbox-boundary failure cases.
- **Workflow C** — knowledge query → `search_knowledge_base` → grounded
  answer, including the C1/C2/C3 cases from `docs/testing.md`.
- **Workflow D** — zero-egress proof (no dedicated asset needed; run
  alongside A/B/C per `docs/demo.md`).
- The documented failure paths in `docs/testing.md` "Failure injection" and
  `docs/document-processing.md`/`docs/api.md` upload-boundary behavior.

Every numeric fact, threshold, and finding below was cross-checked against
the actual backend implementation (not just the design docs) while this
corpus was built — see §14 for what was inspected and why it matters.

## 2. Complete File Inventory

```
test-assets/
├── README.md                                  (this file)
├── knowledge-base/
│   ├── SOP-001-Pump-Maintenance.md             DEMO-CRITICAL
│   ├── SOP-002-Valve-Inspection.md             DEMO-CRITICAL
│   ├── SOP-003-Pressure-Vessel-Inspection.md   DEMO-CRITICAL
│   └── SOP-004-Workplace-Safety.md             DEMO-CRITICAL
├── documents/
│   ├── inspection-report-clean.png             DEMO-CRITICAL
│   ├── inspection-report-degraded.png          DEMO-CRITICAL (optional escalation demo)
│   ├── corrupt-document.png                    TEST-ONLY (failure path)
│   ├── unsupported-document.docx               TEST-ONLY (failure path)
│   └── oversized-test-file.bin                 TEST-ONLY (failure path)
└── prompts/
    ├── rag-test-questions.md                   TEST-ONLY (test script / reviewer aid)
    ├── coding-test-prompts.md                  TEST-ONLY (test script / reviewer aid)
    └── capability-selection-battery.md         TEST-ONLY (benchmark script)
```

## 3. Asset → Workflow Mapping

| Asset | Workflow A | Workflow B | Workflow C | Workflow D |
|---|---|---|---|---|
| `knowledge-base/SOP-00{1..4}-*.md` | ✅ (grounding source) | — | ✅ (primary use) | — |
| `documents/inspection-report-clean.png` | ✅ (primary use — clean OCR pass) | — | ✅ (Section C questions) | — |
| `documents/inspection-report-degraded.png` | ✅ (OCR→vision escalation demo) | — | ✅ (Section C questions) | — |
| `documents/corrupt-document.png` | ✅ (failure-path only) | — | — | — |
| `documents/unsupported-document.docx` | ✅ (upload-boundary rejection only — never reaches the pipeline) | — | — | — |
| `documents/oversized-test-file.bin` | ✅ (upload-boundary rejection only) | — | — | — |
| `prompts/rag-test-questions.md` | (Section C ties into A) | — | ✅ (script for C1/C2/C3) | — |
| `prompts/coding-test-prompts.md` | — | ✅ (script for B1–B4 + extras) | — | ✅ (B4 doubles as a network-denial demo moment) |
| `prompts/capability-selection-battery.md` | (category 1 prompts) | (category 2 prompts) | (categories 3, 6) | — |

Workflow D has no dedicated asset — per `docs/demo.md` it's a standing
property, demonstrated by watching `GET /api/v1/network-status` and the
`network_check` audit events while A/B/C run, not a separate test input.

## 4. Ground Truth — Clean Inspection Report

`documents/inspection-report-clean.png` — a synthetic, printed-style
"PUMP INSPECTION REPORT" form for a fictional cooling water pump, designed to
OCR cleanly (high contrast, no rotation, no handwriting) so it should not
require vision escalation.

| Field | Value |
|---|---|
| Report No. | PIR-2026-0842 |
| Equipment ID | CWP-204A |
| Equipment | Cooling Water Pump — Unit 3 Condenser CW System |
| Location | Utilities Block, Pump House 2 |
| Inspection Date | 2026-08-14 |
| Shift | B |
| Inspector | A. Khandelwal (TTPS-MM-1187) |
| Vibration — Inboard bearing | 5.6 mm/s RMS |
| Vibration — Outboard bearing | **8.3 mm/s RMS** |
| Bearing temp — Inboard | 64 °C |
| Bearing temp — Outboard | 68 °C |
| Mechanical seal leakage | Weeping, ~6 drops/min |
| Coupling guard | Intact, all fasteners secure |
| Lubrication last done | 2026-06-30, NLGI-2 lithium complex |
| Other observation | Minor lubricant discoloration at inboard bearing, flagged for oil analysis |

**Findings printed on the report (5 total):**
1. Outboard vibration 8.3 mm/s RMS → **SOP-001 Band 3 (Alert)**: corrective maintenance within 7 days, notify Area Engineer. *(This is the finding that should clearly map to an explicit SOP-001 rule — use it to judge whether Workflow A's `create_docx` findings are actually traceable to SOP-001, not just to the report text.)*
2. Seal leakage ~6 drops/min → SOP-001 Class II — acceptable, continue monitoring.
3. Bearing temperatures within Normal range — no action.
4. Coupling guard intact — no safety finding.
5. Lubricant discoloration — informational, no threshold exceeded.

Use this ground truth to judge OCR accuracy: a correct `extract_document`
result should recover all the numeric readings above; a correct Workflow A
run should reproduce (or a superset of, worded differently) findings 1–5,
correctly citing SOP-001's Band 3/Class II language for findings 1 and 2.

## 5. Ground Truth — Degraded Inspection Report

`documents/inspection-report-degraded.png` — same form template, describing
a **different but related** pump (CWP-204B, "sister" unit to CWP-204A) a
week later, deliberately degraded to exercise the OCR quality/escalation
pipeline (`docs/document-processing.md`):

- Whole page rotated ~2.3°.
- Gaussian blur applied after rendering.
- ~1.5% random pixel speckle noise (scanner/photocopier-grain simulation).
- The numeric readings and the "Notes" section are rendered in a
  handwriting-style font (`Bradley Hand Bold`), not printed text.
- A deliberately low-contrast/faded rectangular patch is blended directly
  over the handwritten "Notes" lines (still legible on close inspection —
  not destroyed, per the task's "do not make it impossible to understand"
  constraint).
- The measurement table's handwritten values overlap the grid lines more
  than a clean scan would, adding minor layout-parsing difficulty.

| Field | Value |
|---|---|
| Report No. | PIR-2026-0855 |
| Equipment ID | CWP-204B |
| Location | Utilities Block, Pump House 2 |
| Inspection Date | 2026-08-21 |
| Shift | C |
| Inspector | R. Nair (handwritten) |
| Vibration — Inboard | 7.1 mm/s RMS (handwritten) |
| Vibration — Outboard | **9.8 mm/s RMS** (handwritten) |
| Bearing temp — Inboard | 76 °C (handwritten) |
| Bearing temp — Outboard | **91 °C** (handwritten) |
| Mechanical seal leakage | "steady drip, approx 25 drops/min" (handwritten) |
| Coupling guard | "intact, OK" (handwritten) |
| Notes (faded region) | "outboard temp climbing since last week - re-check tomorrow, flagged to shift engineer" |

**Intended findings, per SOP-001:**
1. Outboard vibration 9.8 mm/s RMS → Band 3 (Alert): corrective maintenance within 7 days.
2. Outboard bearing temp 91 °C → **Band/Critical (>85 °C): immediate shutdown required.** This is the escalation-worthy finding — a correct Workflow A run on this asset must not omit or soften it into a lesser finding just because the source reading was handwritten and lower-confidence.
3. Seal leakage ~25 drops/min → Class III: schedule seal replacement within 30 days.

**Expected pipeline behavior:** PaddleOCR runs the primary pass on every
document (`docs/document-processing.md` step 1); quality signals (mean
confidence, completeness, handwriting/layout flags — thresholds in
`config/app.yaml`: `mean_confidence_below: 0.75`, `completeness_below: 0.6`)
should plausibly cross at least the confidence and/or completeness
thresholds given the blur/noise/handwriting, triggering escalation to the
`vision` resource type; the final result should still surface the Critical
91 °C finding, with `warnings` noting reduced confidence rather than
silently dropping or rounding the reading. See §14 for an important caveat
on the `handwriting_detected`/`layout_complexity_flag` signals specifically.

## 6. Which SOP Contains Which Facts

| SOP | Covers | Distinctive numeric facts |
|---|---|---|
| SOP-001 (Pump Maintenance) | Vibration bands, lubrication, bearing temp, mechanical seal leakage (Class I–IV), coupling/guard, escalation, return-to-service | Vibration: ≤4.5/≤7.1/≤11.0/>11.0 mm/s RMS; bearing temp ≤70/≤85/>85 °C; seal Class I–IV at 0/≤10/≤60/>60 drops/min; re-grease every 2000h or 90 days |
| SOP-002 (Valve Inspection) | External leak grading (A–D), isolation (double block & bleed / blank), LOTO for valves, return-to-service | Leak Grade A–D at 0/weeping/<1 drop per 10s/≥1 drop per 10s; inspection every 90/180 days |
| SOP-003 (Pressure Vessel Inspection) | Inspection intervals, corrosion/thickness classification, relief valve tolerance, MAWP/bulging escalation, documentation | External visual: 6 months; internal: 24 months; UT survey: 48 months; thickness ≥1.25×/≥1.0×/<1.0× t-min; relief valve ±3%; records retained life+5 years |
| SOP-004 (Workplace Safety) | PPE, PTW categories/validity, LOTO mechanics, isolation verification, confined space, emergency procedures, restricted work | PTW max 12h/shift; hot work near fuel: 15m, 2h permit, re-test every 30 min; confined space O2 19.5–23.5%, LEL <10% |

Cross-references are deliberate: SOP-001 §6 and SOP-002 §5 both point to
SOP-004 for LOTO mechanics; SOP-003 §2 points to SOP-004 for vessel-entry
isolation. Use these when testing multi-document reasoning (see
`prompts/rag-test-questions.md` Section C/E).

## 7. RAG Questions and Expected Evidence

Full detail in `prompts/rag-test-questions.md` (Sections A–E, mapped to
`docs/testing.md`'s C1/C2/C3 cases). Summary:

- **Section A/B (8 + 4 questions)** — C1 cases: definitely-covered, single-SOP
  facts, including deliberately similar-sounding cross-SOP thresholds (B1–B4)
  to test retrieval doesn't conflate SOP-001's pump-seal classes with
  SOP-002's valve-leak grades.
- **Section C (4 questions)** — combines a specific inspection-report reading
  (§4/§5 above) with an SOP rule; a correct answer must cite the actual
  numeric reading from the report, not a generic restatement of the SOP.
- **Section D (6 questions)** — C2 cases: genuinely uncovered topics,
  including two "near-miss" questions (D4 gearbox temp, D6 crane) deliberately
  adjacent to covered topics, to test grounding honesty rather than topic
  proximity.
- **Section E (4 conversations)** — C3 cases: multi-turn retrieval judgment,
  covering "no new retrieval needed," "new retrieval needed (different
  sub-topic)," "recovering after a no-grounding turn," and "same concept,
  different equipment class."

## 8. Expected OCR Behavior — Clean vs. Degraded

| | Clean | Degraded |
|---|---|---|
| Expected `extraction_method` | `ocr` | `ocr` or `vision_escalation` (see §14 caveat) |
| Expected `confidence` | High (comfortably above the 0.75 mean-confidence escalation threshold) | Likely lower; may fall below 0.75 and/or the 0.6 completeness threshold |
| Expected `warnings` | Empty or none | Should include at least one warning about reduced confidence, or (if vision escalation genuinely fires and succeeds) a method-change note; must **not** silently omit the 91 °C Critical reading |
| Escalation expected? | No | Plausible (see §14) — do not treat "did not escalate" alone as a bug without checking the actual signal values in `data/extraction/{document_id}.json` first |

## 9. Expected Failure Behavior — Corrupt / Unsupported / Oversized

All three are verified against the actual code in `backend/api/documents.py`,
`backend/domain/document_processing/pipeline.py`, and
`backend/domain/capabilities/extract_document.py` — not just the design docs.

### `corrupt-document.png`
A PNG with a valid 8-byte signature and a structurally-present but
CRC-invalid, truncated `IHDR` chunk followed by random bytes — no `IDAT`/
`IEND`. Verified locally: `PIL.Image.open(...).load()` raises
`UnidentifiedImageError`.
- **Upload (`POST /api/v1/documents`):** succeeds — the endpoint only checks
  the client-declared `Content-Type` header and byte size, not actual image
  validity (`backend/api/documents.py::_validate_upload`). Upload with
  `-F "file=@corrupt-document.png;type=image/png"`.
- **`extract_document` capability:** the primary OCR pass's `PIL`/PaddleOCR
  call raises on this file; `pipeline.py` wraps any such exception into
  `UnreadableDocumentError`, which `extract_document.py` turns into a
  `status: "failed"` capability result — **not** a crash, **not** a silent
  empty-but-successful extraction. This is the exact contract in
  `docs/capabilities.md`/`docs/document-processing.md` "Failures".

### `unsupported-document.docx`
A minimal, valid DOCX (openable, verified with `python-docx`) containing only
harmless placeholder text — no organizational data.
- **`POST /api/v1/documents`:** rejected with **`400 INVALID_MIME_TYPE`** —
  the allowlist (`backend/api/documents.py::ALLOWED_MIME_TYPES`) is exactly
  `image/jpeg`, `image/png`, `application/pdf`; DOCX is not in it. Upload
  with `-F "file=@unsupported-document.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"`
  to make sure the client declares the real MIME type (some HTTP clients
  guess a MIME type from the extension differently — set it explicitly).
- **`POST /api/v1/knowledge-base/documents`:** also rejected, same
  `400 INVALID_MIME_TYPE` — the KB ingestion allowlist
  (`backend/api/knowledge_base.py::ALLOWED_EXTENSIONS`) is `.txt`, `.md`,
  `.markdown`, `.pdf`; `.docx` matches neither the extension nor content-type
  allowlist there either. Both endpoints are worth testing against this file.

### `oversized-test-file.bin`
10,600,000 bytes of generated filler (a repeating byte pattern, no real
content) — ~114 KB over the actual configured limit, not an arbitrarily huge
file.
- **Configured limit:** `config/capabilities.yaml` →
  `extract_document.max_file_size_mb: 10` → exactly **10,485,760 bytes**
  (`backend/api/documents.py::MAX_FILE_SIZE_BYTES`), matching
  `docs/document-processing.md`'s documented 10MB default.
- **Expected response:** `400 FILE_TOO_LARGE`, with `details.max_size_bytes:
  10485760` and `details.actual_size_bytes: 10600000`.
- **Important:** `_validate_upload` checks MIME type **before** size
  (`backend/api/documents.py` lines ~60–100). Since this file's extension is
  `.bin`, you must explicitly declare an allowed `Content-Type` when
  uploading it, or you'll get `400 INVALID_MIME_TYPE` instead of the size
  error you're actually testing for:
  ```bash
  curl -s -X POST localhost:8000/api/v1/documents \
    -F "file=@oversized-test-file.bin;type=image/png"
  ```

## 10. Coding Test Mapping

`prompts/coding-test-prompts.md` maps directly to `docs/testing.md`'s B1–B4:

| Test case | Asset section | Verifies |
|---|---|---|
| B1 | "B1 — Successful coding task" | Correct `generate_code`→`execute_code` sequencing, deterministic output |
| B2 | "B2 — Successful execution interpretation" | Correct stdout interpretation and termination without redundant re-execution |
| B3 | "B3 — Deliberate correction-loop task" | A genuine (not manufactured) first-attempt bug, correction, and a **second, distinct** execute step |
| B4 | "B4a/B4b — Network / package-install security tasks" | `--network none` and read-only-filesystem sandbox enforcement actually hold; Orchestrator reports failure honestly, never fabricates success |
| Extras 1–3 | "Additional industrial-data calculation tasks" | General deterministic-calculation coverage beyond the minimum 4 cases |

All expected outputs were hand-computed and are exact — see the file for the
arithmetic. Sandbox facts (stdlib-only image, `--read-only`, `--network
none`, 30s/512MB/1cpu limits) were verified against
`sandbox/Dockerfile` and `backend/domain/sandbox/docker_executor.py`, not
assumed from `docs/sandbox.md` alone.

## 11. Capability-Selection Battery Mapping

`prompts/capability-selection-battery.md` provides 24 prompts (4 per
category, above the ≥20 minimum) matching `docs/testing.md`'s six battery
categories exactly:

1. Clearly OCR-needing (#1–4) → `extract_document`
2. Clearly code-needing (#5–8) → `generate_code`/`execute_code`
3. Clearly retrieval-needing (#9–12) → `search_knowledge_base`
4. Directly answerable (#13–16) → `respond`, no capability
5. Superficially tool-like but direct (#17–20) → `respond`, no capability
6. Retrieval-shaped but uncovered (#21–24) → `search_knowledge_base`
   attempted, honest no-grounding `respond`

No prompt in this file uses `create_docx`/`create_xlsx` — the battery in
`docs/testing.md` doesn't require artifact-generation coverage, and Workflow
A already exercises `create_docx` end-to-end (§4/§5 above).

## 12. Demo-Critical vs. Test-Only Assets

**Demo-critical** (needed for a live SIH run-through of `docs/demo.md`):
- `knowledge-base/SOP-001..004-*.md` — the entire knowledge base must be
  seeded and `ready` before Workflows A or C are demoable at all.
- `documents/inspection-report-clean.png` — the primary Workflow A asset.
- `documents/inspection-report-degraded.png` — optional but recommended: the
  documented "ideally one deliberately lower-quality asset to show
  escalation" from `docs/demo.md` Workflow A.

**Test-only** (never shown to judges; used for manual/automated test passes):
- `documents/corrupt-document.png`, `unsupported-document.docx`,
  `oversized-test-file.bin` — all three exist solely to exercise documented
  failure paths (§9).
- `prompts/*.md` — test scripts and benchmark aids for a human reviewer or
  the Orchestrator benchmark procedure in `docs/testing.md`; not artifacts
  the system itself consumes.

## 13. Ingestion Order for the SOPs

Retrieval is pure vector similarity with no ordering dependency
(`docs/rag.md` "Reranking" — none for SIH), so ingestion order does not
affect retrieval *correctness*. For a predictable, repeatable manual test
session, ingest in numeric order:

```bash
for f in SOP-001-Pump-Maintenance SOP-002-Valve-Inspection \
         SOP-003-Pressure-Vessel-Inspection SOP-004-Workplace-Safety; do
  curl -s -X POST localhost:8000/api/v1/knowledge-base/documents \
    -F "file=@test-assets/knowledge-base/${f}.md;type=text/markdown" \
    -F "metadata={\"title\":\"${f}\",\"category\":\"sop\"}"
done
```

## 14. How to Know the KB Is Ready Before Workflow A/C

Poll `GET /api/v1/knowledge-base` until **all four** documents show
`"status": "ready"` (not `"ingesting"` or `"failed"`) — per `docs/rag.md`,
ingestion (parse → chunk → embed → index) runs as a background task, so the
`202` from the ingest call is not itself readiness. `chunk_count` should be
non-zero for each. Only once all four show `ready` should Workflow A/C be
run — a query against a partially-ingested KB is a false negative, not a
real retrieval-quality signal.

## 15. Implementation-Specific Constraints Discovered

These were found by reading the actual backend code (per `AGENTS.md` §3 —
"the code is the source of truth"), not assumed from the docs:

- **`handwriting_detected`/`layout_complexity_flag` depend on PaddleOCR's
  layout-classification labels being populated** (`backend/domain/document_processing/ocr.py::_region_type_from_layout`
  only returns `"handwriting"`/`"table"` when the underlying PaddleOCR
  `predict()`/`ocr()` call actually returns a `layout_det_res`/
  `layout_result` structure with those labels — not guaranteed by every
  PaddleOCR pipeline configuration). This corpus's degraded report was
  designed to reliably trigger escalation via the two signals that do
  **not** depend on layout classification — lower `mean_ocr_confidence`
  (blur/noise) and lower `completeness_estimate` (handwritten text is
  typically sparser/lower-density than printed text of the same content) —
  rather than relying on the handwriting/table signals specifically firing.
  If escalation does not trigger on the degraded asset in your environment,
  check `data/extraction/{document_id}.json`'s `signals` block before
  assuming a bug — it may simply mean this PaddleOCR build's layout labels
  differ, and the confidence/completeness signals are the ones to look at.
- **MIME validation order matters for testing the size limit**: `POST
  /api/v1/documents` checks the declared MIME type before file size
  (`backend/api/documents.py::_validate_upload`), so `oversized-test-file.bin`
  must be uploaded with an explicit allowed `Content-Type` (see §9) or you'll
  observe the wrong error code.
- **DOCX is rejected at two independent boundaries** (`/documents` and
  `/knowledge-base/documents`), each with its own allowlist
  (`ALLOWED_MIME_TYPES` vs. `ALLOWED_EXTENSIONS`/`ALLOWED_CONTENT_TYPES`) —
  both were verified in code as part of preparing this corpus; no
  discrepancy from `docs/api.md`/`docs/document-processing.md` was found.
- **`search_knowledge_base`'s relevance floor is a named constant in
  code** (`backend/domain/rag/retrieval.py::RELEVANCE_FLOOR = 0.50`, using a
  `1 / (1 + distance)` conversion from Chroma's raw L2 distance) — this is
  what makes the Section D "not covered" questions in
  `prompts/rag-test-questions.md` reliably return `results: []` rather than
  a low-quality-but-nonempty hit; it is not currently documented as a named
  value anywhere in `docs/rag.md` itself, worth knowing if a "not covered"
  question unexpectedly returns a weak match.
- No other discrepancy between the `docs/` contracts and the actual
  implementation was found while preparing this corpus — behavior for
  MIME allowlists, size limits, error codes, and the OCR failure path all
  matched `docs/api.md`, `docs/document-processing.md`, and
  `docs/capabilities.md` as documented, and matches the independently
  code-verified `docs/api-manual-testing-guide.md` written in a prior
  session.

## 16. Validation Performed

- All 12 files listed in §2 exist on disk at the paths shown.
- Every SOP was checked for internal numeric consistency (no contradicting
  thresholds within or across documents) and for the deliberate
  cross-references described in §6.
- Every fact cited in `prompts/rag-test-questions.md` Sections A–C was
  checked against the actual SOP/report text it claims to come from.
- Section D "not covered" questions were checked against all four SOPs'
  full text to confirm no accidental coverage exists.
- `inspection-report-clean.png` and `inspection-report-degraded.png` ground
  truth (§4/§5) was authored from the same generation script that produced
  the images, so the documented "ground truth" and the rendered pixels are
  guaranteed to agree.
- `unsupported-document.docx` was round-tripped through `python-docx` to
  confirm it opens as a valid document.
- `oversized-test-file.bin`'s size (10,600,000 bytes) was checked against
  the actual configured limit (10,485,760 bytes) read from
  `config/capabilities.yaml`, not the documentation's "10MB default" alone.
- `corrupt-document.png` was checked against `PIL.Image.open(...).load()`
  locally to confirm it raises `UnidentifiedImageError`, matching what
  `backend/domain/document_processing/pipeline.py` catches and converts to
  `UnreadableDocumentError`.
- No new API endpoint, capability, event type, database field, or
  architectural behavior was introduced or assumed anywhere in this corpus
  or its documentation.

**Still requiring manual/live-environment review** (could not be verified
without running the actual backend, Ollama, PaddleOCR, and Chroma, which
this task was scoped not to require):
- Whether `inspection-report-degraded.png` actually triggers vision
  escalation in a live run (see §15's caveat) — the design targets the
  confidence/completeness signals specifically because the
  handwriting/layout signals' behavior depends on the installed PaddleOCR
  build's layout-detection output, which cannot be verified without running
  it.
- The real OCR confidence PaddleOCR reports on `inspection-report-clean.png`
  — designed to be comfortably above the 0.75 threshold, but the actual
  number depends on the installed PaddleOCR model weights.
- Actual retrieval scores for the RAG questions in `prompts/rag-test-questions.md`
  against `qwen3-embedding:0.6b` — the questions were designed for topical/
  lexical alignment with specific SOP passages, but exact similarity scores
  relative to the 0.50 floor can only be observed live.
