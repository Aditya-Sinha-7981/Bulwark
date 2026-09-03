# SIH Demo Workflows

The bridge between engineering and the final presentation. These four flows are the entire SIH-critical scope — see `requirements.md`'s MVP section. Nothing here should surprise anyone who's read `architecture.md`, `agent.md`, and `capabilities.md`; this file just walks the same system through the specific demo path.

---

## Workflow A — Scanned report → SOP retrieval → findings → DOCX

**Starting state:** Knowledge base seeded and `ready`; a synthetic scanned inspection report image prepared.

**User action:** Uploads the report image, asks the system to review it and draft an approval note.

**Expected Orchestrator behavior:**
1. Proposes `extract_document` with the uploaded `document_id`.
2. Reads the extracted text; proposes `search_knowledge_base` to ground findings against relevant SOPs.
3. Composes structured findings (not prose formatting) from the extracted content plus retrieved context.
4. Proposes `create_docx` with those findings as structured `arguments`.
5. Responds with a summary referencing the generated artifact.

**Policy decisions:** `allow` on all three capability proposals (assuming valid inputs — no reason for a demo-path denial).

**Model/resource usage:** `vision` resource type only if the extraction pipeline's internal tiering escalates (depends on scan quality — plan the demo asset to exercise at least one clean pass and, ideally, one deliberately lower-quality asset to show escalation); `embedding` for retrieval; `reasoning` throughout for orchestration and findings composition.

**Intermediate results, visible in the trace:** `tool_invoked: extract_document` → result → `tool_invoked: search_knowledge_base` → results (rendered in the RAG evidence panel) → `tool_invoked: create_docx` → `artifact_created`.

**Final result:** A downloadable DOCX approval note, linked in the Artifact panel.

**Failure behavior:** If extraction confidence is low even after escalation, findings should note the uncertainty rather than presenting fabricated confidence — verify this specifically if using a deliberately degraded demo asset.

**Success criteria:** Correct capability sequencing (extraction → retrieval → generation, not skipped or reordered), a schema-valid DOCX produced, findings traceable to both the extracted text and retrieved SOP content.

---

## Workflow B — Coding request → generation → sandbox execution → verification

**Starting state:** Sandbox image built (`bulwark-sandbox:latest`), Docker Desktop running.

**User action:** Asks for a small script solving a defined task (e.g., a calculation relevant to the industrial context).

**Expected Orchestrator behavior:**
1. Proposes `generate_code`.
2. Proposes `execute_code` with the generated code.
3. Reads the execution result; if it failed, proposes a corrected `generate_code`/`execute_code` pair (bounded by the step limit).
4. Responds with the verified result and the code.

**Policy decisions:** `allow` on both capability proposals; Policy's `network_access` invariant check on `execute_code` is a good moment to narrate during the demo — "note this is checked even though we already know the sandbox has no network."

**Model/resource usage:** `code_generation` for generation, no resource for execution (deterministic sandbox).

**Intermediate results, visible in the trace:** `tool_invoked: generate_code` → `tool_invoked: execute_code` → stdout/exit code → (if a retry occurs) a second generation/execution pair, clearly distinct in the trace.

**Final result:** Verified working code plus its output, shown in chat.

**Failure behavior:** A deliberately buggy first attempt is actually a *good* demo moment if rehearsed — shows the correction loop rather than hiding it.

**Success criteria:** Generation and execution appear as distinct, separately-audited steps; correct interpretation of the sandbox result; correct termination once verified.

---

## Workflow C — Local knowledge query → explicit retrieval → grounded answer

**Starting state:** Knowledge base seeded and `ready`.

**User action:** Asks a question answerable from the seeded synthetic SOPs.

**Expected Orchestrator behavior:** Proposes `search_knowledge_base` directly, then composes a grounded answer — typically the shortest of the four workflows, a good one to open the demo with.

**Policy decisions:** `allow` on the retrieval proposal.

**Model/resource usage:** `embedding` for the query, `reasoning` for composing the grounded answer.

**Intermediate results:** `tool_invoked: search_knowledge_base` → results, shown in the RAG evidence panel alongside the final chat answer.

**Final result:** A grounded chat answer citing the retrieved SOP content.

**Failure behavior:** If asked something the seeded knowledge base genuinely doesn't cover, the correct behavior is an honest "I don't have grounding for that" — worth demonstrating deliberately once, since it's a stronger trust signal than only showing successful retrievals.

**Success criteria:** Retrieval is explicit and visible in the trace (never implicit); the answer is traceable to specific retrieved chunks.

---

## Workflow D — Visible zero-egress proof

**Starting state:** The Sovereignty Indicator panel visible in the frontend throughout the entire demo session, not activated specially for this moment.

**User action:** None specific — this is a standing property, demonstrated by pointing at the panel (and, if pressed, the Audit log) at any point, ideally while Workflows A/B/C are actively running so it's clearly not a static/faked indicator.

**Expected behavior:** `GET /api/v1/network-status` continuously shows `external_connections_detected: false`; `network_check` audit events accumulate in the background, independent of any specific Job.

**What to show judges, concretely:** (1) the live panel, ideally captured running concurrently with a Job like Workflow B's sandbox execution — the moment code is actually running is a good time to point at it; (2) if asked to prove it further, a query against the Audit log showing zero non-loopback connections across every `model_invoked`/`tool_invoked` event in the session.

**Success criteria:** The panel is visibly live (updating), not a static claim; a technically-literate judge's follow-up question ("how do you know?") has a real answer pointing at both the enforcement layers (`security.md`) and the retroactive audit query — not just "trust the UI."

---

## Demo sequencing note

Recommended order for a live run-through: **C → A → B**, with **D** narrated continuously throughout rather than as a separate segment. C is the shortest/safest opener; A demonstrates the full multimodal-to-deliverable chain; B is the most interactive (and benefits most from the visible-swap/correction-loop narration). Rehearse the model-swap moments (`resource_loaded` events appearing in the trace) as a feature to point at, not a pause to apologize for.
