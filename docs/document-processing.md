# Document Processing (OCR / Vision Extraction)

## Principle

The Orchestrator sees exactly one capability — `extract_document` (`capabilities.md`). Everything below happens *inside* that capability's Executor; the tiering is never exposed as separate Orchestrator-visible steps (ADR-04, `decisions.md`).

## Supported file types

Scanned document images (JPEG/PNG), scanned PDFs (page images), photographs of physical documents or handwritten notes. Validated against an allowlist of MIME types at upload time (`POST /api/v1/documents`); anything else is rejected with a `400` before it ever reaches this pipeline.

## Storage

Uploaded originals: `data/uploads/{document_id}.{ext}`. Intermediate extraction output (raw OCR text, confidence data): `data/extraction/{document_id}.json` — kept for debugging/audit, not user-facing.

## Pipeline

1. **Primary pass — PaddleOCR (PP-OCRv6), CPU.** Runs on every document, every time. Produces recognized text, per-region confidence scores, and layout structure (columns, tables, detected regions).

2. **Quality assessment — multiple signals, not one confidence number** (explicitly required, ADR-04):
   - Mean recognition confidence across regions
   - Detected handwriting-style regions (from PaddleOCR's layout/region classification)
   - Extraction completeness — recognized text density versus what the detected layout suggests should be present
   - Layout complexity flags — multi-column or table structures the engine's structure module didn't resolve cleanly

3. **Escalation decision.** If **any** of the above signals crosses its configured threshold (see `configuration.md` for exact thresholds — kept configurable, not hardcoded), escalate *that specific image* (not the whole document/Job) to the `vision` resource type.

4. **Vision escalation pass** — `qwen3.5:9b` (per `models.md`) given the image directly, prompted to extract/transcribe the content, particularly for handwritten regions the OCR pass flagged as low-confidence.

5. **Result assembly** — the capability's output (`capabilities.md`) reports `extraction_method: ocr` or `extraction_method: vision_escalation`, the final `extracted_text`, an overall `confidence`, and any `warnings` (e.g., "handwritten section on page 2 could not be confidently transcribed").

## Handwriting detection

A signal within step 2, not a separate pipeline — PaddleOCR's region/layout output is used to flag likely-handwritten regions (distinguished from printed text by the engine's own classification), which contributes to the escalation decision independent of raw confidence score.

## Layout issues

Complex multi-column layouts or embedded tables that the OCR engine's structure module misreads are one of the explicit multi-signal escalation triggers (step 3) — not silently accepted as correct just because individual characters were recognized with high confidence.

## Extraction artifact format

Stored at `data/extraction/{document_id}.json`:

```json
{
  "document_id": "uuid",
  "extraction_method": "ocr | vision_escalation",
  "extracted_text": "string",
  "confidence": 0.0,
  "signals": {
    "mean_ocr_confidence": 0.0,
    "handwriting_detected": false,
    "completeness_estimate": 0.0,
    "layout_complexity_flag": false
  },
  "warnings": ["string"],
  "processed_at": "iso8601"
}
```

This is intermediate/debug data — the capability's actual return value to the Orchestrator is the smaller schema in `capabilities.md`.

## Limits

Max input file size and max processing timeout are configuration values (`configuration.md`), not hardcoded — default 10MB per document, 120s total processing time (covering both OCR and, if triggered, vision escalation).

## Failures

- Corrupt/unreadable file → capability returns `status: failed` with a clear error, never a silent empty extraction.
- OCR succeeds but confidence remains low even after vision escalation → capability still returns `status: succeeded` with `extracted_text` and prominent `warnings` — the Orchestrator, not the Executor, decides whether that's good enough to proceed (e.g., it might still draft findings but flag low confidence in the final DOCX, or it might ask the user for a clearer scan).
- Vision model unavailable during an escalation attempt → falls back to reporting the OCR-only result with a warning noting escalation was needed but unavailable, rather than failing the whole capability.

## Security controls

Uploaded files are never executed, never parsed by anything beyond the OCR/vision pipeline's own libraries, and are scoped to read-only access within this capability's Executor — no other component reads `data/uploads/` directly except through this pipeline or the artifact/document metadata endpoints in `api.md`.
