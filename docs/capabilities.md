# Capabilities

Every capability the Orchestrator can propose, as an explicit contract. Capability names here are canonical — used identically in the Capability Registry, the Orchestrator's proposal schema (`agent.md`), Policy rules, and Audit events. Do not rename or add a capability without updating this file first.

## Common contract shape

Every capability declares:

```yaml
name: string
purpose: string
resource_type: reasoning | code_generation | vision | embedding | null   # null = deterministic, no model
permissions: [ ... ]
network_access: false   # always false in this system; present for explicitness, never overridden
filesystem_scope: [ ... ]
timeout_seconds: integer
retry_policy: string
```

Every invocation produces `tool_invoked` and (on completion) an outcome audit event; a failure produces `error`.

---

## `extract_document`

**Purpose:** Extract text/structured content from an uploaded document image (scanned report, handwritten note, photograph). Internally tiered — see `document-processing.md` for the OCR → escalation logic. This tiering is invisible to the Orchestrator; it sees one capability, one result.

**Resource type:** `vision` (only when internal escalation triggers it — the base OCR pass is deterministic, no resource type).

**Input schema:**
```json
{ "document_id": "uuid" }
```

**Output schema:**
```json
{
  "extracted_text": "string",
  "extraction_method": "ocr | vision_escalation",
  "confidence": 0.0,
  "warnings": ["string"]
}
```

**Permissions:** read `data/uploads/{document_id}`.
**Filesystem scope:** read-only, the referenced document only.
**Timeout:** 60s (OCR pass), up to 120s total if escalation triggers.
**Retry:** none automatic — a failure is returned to the Orchestrator as a tool result, not silently retried.
**Failure modes:** unreadable file, extraction confidence critically low even after escalation (returned as a warning, not a hard failure — the Orchestrator decides how to proceed).

---

## `search_knowledge_base`

**Purpose:** Explicit retrieval against the local knowledge base.

**Resource type:** `embedding` (for the query embedding step; retrieval itself is deterministic).

**Input schema:**
```json
{ "query": "string", "top_k": 5 }
```

**Output schema:**
```json
{
  "results": [
    { "kb_document_id": "uuid", "title": "string", "chunk_text": "string", "score": 0.0 }
  ]
}
```

**Permissions:** read Chroma index.
**Filesystem scope:** none directly (Chroma-managed storage).
**Timeout:** 10s.
**Retry:** none.
**Failure modes:** empty knowledge base, no results above a relevance floor (returned as an empty `results[]`, not an error — the Orchestrator must handle "no grounding found" honestly, see `agent.md`).

---

## `generate_code`

**Purpose:** Produce code for a described task. Does not execute it — see `execute_code`.

**Resource type:** `code_generation`.

**Input schema:**
```json
{ "task_description": "string", "language": "python" }
```

**Output schema:**
```json
{ "code": "string", "language": "python", "explanation": "string" }
```

**Permissions:** none (pure generation, no filesystem/network access).
**Filesystem scope:** none.
**Timeout:** 30s.
**Retry:** none automatic.
**Failure modes:** malformed/empty generation (returned as a tool error).

---

## `execute_code`

**Purpose:** Run generated code in the isolated Docker sandbox and capture the result.

**Resource type:** null (deterministic — the sandbox itself, no model).

**Input schema:**
```json
{ "code": "string", "language": "python", "input_files": ["document_id", "..."] }
```

**Output schema:**
```json
{
  "stdout": "string",
  "stderr": "string",
  "exit_code": 0,
  "timed_out": false,
  "output_files": ["artifact_id", "..."]
}
```

**Permissions:** create/run a Docker container; read designated input mount; write designated output mount.
**Filesystem scope:** the sandbox's own ephemeral workspace only (`data/sandbox/{execution_id}/`) — see `sandbox.md`.
**Network access:** `false`, enforced by `--network none` at the Docker level, not just declared.
**Timeout:** 30s default (configurable, see `configuration.md`), hard-killed on expiry.
**Retry:** none automatic.
**Failure modes:** non-zero exit, timeout, container crash — all returned as structured results, not exceptions; the Orchestrator decides whether to retry via a fresh `generate_code`/`execute_code` pair.

---

## `create_docx`

**Purpose:** Deterministically render a Word document from structured findings.

**Resource type:** null (deterministic).

**Input schema:**
```json
{
  "title": "string",
  "sections": [ { "heading": "string", "body": "string" } ],
  "metadata": { "prepared_by": "string", "date": "iso8601" }
}
```

**Output schema:**
```json
{ "artifact_id": "uuid", "filename": "string" }
```

**Permissions:** write `data/artifacts/`.
**Filesystem scope:** write-only, artifact output directory.
**Timeout:** 15s.
**Retry:** none automatic.
**Failure modes:** invalid input schema (rejected before rendering — never a partially-written file).

---

## `create_xlsx`

**Purpose:** Deterministically render an Excel file from structured tabular data.

**Resource type:** null (deterministic).

**Input schema:**
```json
{
  "title": "string",
  "sheets": [ { "name": "string", "headers": ["string"], "rows": [["cell", "..."]] } ]
}
```

**Output schema:** same shape as `create_docx`.

**Permissions/scope/timeout/failure modes:** same pattern as `create_docx`.

**Note:** not exercised by any of the four SIH demo workflows — included for contract completeness per `requirements.md` (F6), not required to be demo-validated.

---

## `create_pptx` (deferred)

Same contract shape as `create_docx`. Declared in the registry for completeness but not built for SIH unless a demo workflow comes to need it — see `requirements.md`, deferred scope.

---

## Specialist model-backed invocation (generic pattern)

Any capability with a non-null `resource_type` follows this pattern inside its Executor: request the resource type from the Model Runtime → Lifecycle Manager resolves/loads the configured model → invoke it with the capability's specific prompt/schema → validate the output against the capability's output schema before returning it. This validation step is what catches a malformed model response before it reaches the Orchestrator as a "successful" tool result.

## Policy checks (summary — full detail in `security.md`)

Every capability invocation is checked against: is this capability enabled, does the caller (always the Orchestrator, always the same trust level) have the declared permissions, is `network_access` false (it always must be, checked as an invariant, not a per-call judgment), are inputs within declared filesystem scope, are resource limits (timeout, output size) within configured bounds.
