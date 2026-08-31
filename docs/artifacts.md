# Artifact Generation

## Principle

The model produces structured data; deterministic application code renders the file. The model never controls formatting directly (ADR-10, `decisions.md`) — this is a hard boundary, not a style preference.

## Supported types

DOCX (`python-docx`), XLSX (`openpyxl`). PPTX is declared in the capability contract (`create_pptx`, `capabilities.md`) for completeness but deferred — not built unless a demo workflow requires it.

## Structured input schemas

Exactly as declared per-capability in `capabilities.md` (`create_docx`, `create_xlsx`, `create_pptx`). Restated here isn't necessary — `capabilities.md` is authoritative for these schemas; this file covers the *rendering* side.

## Renderer responsibilities

Given a validated structured-data payload (schema-checked before rendering ever begins — an invalid payload is rejected, never partially rendered), the renderer:

1. Loads a fixed template (see Templates, below).
2. Populates it with the payload's content.
3. Applies consistent formatting (heading styles, fonts, spacing) — fixed by the template, not decided per-invocation.
4. Writes the output file to `data/artifacts/{artifact_id}.{ext}`.
5. Returns `{ artifact_id, filename }` (matching the capability's output schema).

## Templates

**DOCX (approval note / findings document):** title, a metadata block (prepared-by, date), then one section per `sections[]` entry (heading + body paragraph). A single, simple, professional template — not a per-request stylistic decision. Defined once in `backend/services/artifacts/docx_template.py` (or equivalent — see `backend.md` for the module layout).

**XLSX:** one sheet per `sheets[]` entry, first row = `headers`, subsequent rows = `rows`, basic header-row bold styling. No charts/formulas for SIH scope.

## Formatting rules

Fixed by the template code, not influenced by model output beyond the content itself. The model supplies *what* goes in a section; the renderer decides *how* it looks.

## Naming

`{artifact_id}.{ext}` on disk (collision-proof by construction, since `artifact_id` is a UUID); the user-facing `filename` returned in the API/capability response is a readable name derived from the `title` field in the input payload (e.g., `Approval_Note_2026-08-30.docx`), used for the `Content-Disposition` header on download (`api.md`).

## Metadata

Stored on the `Artifact` row (`data-model.md`) — `type`, `filename`, `job_id`, `size_bytes`, `created_at`. Not embedded as document properties inside the file itself for SIH scope (no requirement for that).

## Validation

Input payload is validated against the capability's JSON schema (`capabilities.md`) before any rendering begins. A validation failure returns a failed `CapabilityExecution` result to the Orchestrator — the Orchestrator can then correct its `create_docx`/`create_xlsx` arguments and retry (a new proposal, counts against the step limit per `agent.md`).

## Storage

`data/artifacts/` — see `deployment.md` for the full filesystem layout. Not cleaned up automatically; artifacts persist for the life of the local deployment (no retention policy needed at SIH scale, consistent with `data-model.md`).

## Download

`GET /api/v1/artifacts/{artifact_id}/download` (`api.md`) streams the file with an appropriate `Content-Disposition` header. The frontend's artifact panel (`frontend.md`) links directly to this endpoint.

## Failure handling

Rendering failures (malformed payload, disk write error) are captured and returned as a failed capability result — never a partially-written, corrupted file left in `data/artifacts/`. The renderer writes to a temp path first and only moves the file into `data/artifacts/` on full success (atomic rename), so a failure never leaves a broken file where the Artifact row would otherwise point.
