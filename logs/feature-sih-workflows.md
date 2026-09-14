# logs/feature-sih-workflows.md

> Feature / workstream: `sih-workflows` (Task 19 — SIH workflow validation)
> Branch: `feature/sih-workflows`, branched from `feature/zero-egress` (itself from `fix/kb-upload-ui` / `main`) 2026-09-14
> Started: 2026-09-14
> Status: complete as a validation task — **two real regressions found and filed** (not fixed here, per this task's own scope: validation only, no application code changes)

## Goal

Per `tasks/19-sih-workflow-validation.md`: run each of the four `docs/demo.md` workflows ≥5× against the real, integrated, zero-egress-hardened system (real Ollama, real Docker sandbox, real seeded knowledge base), through the API (per the task's own guidance to automate scriptable runs), and report whether the documented hard thresholds (100% termination, ≥80% task success per workflow, ≥95% structured-output validity) actually hold — not once, but repeatedly. This is explicitly the task where "it worked once in integration" (Task 17) either becomes "it works every time," or a real regression gets found and routed to its owning task.

## Assets prepared (`tests/fixtures/demo_assets/`)

- **Knowledge base:** 3 new synthetic SOPs, team-authored, realistic (not lorem-ipsum) — `sops/SOP-100-Centrifugal-Pump-Maintenance.md`, `sops/SOP-204-Conveyor-Belt-Safety-Inspection.md`, `sops/SOP-311-Electrical-Panel-Lockout-Tagout.md`. Ingested into the real KB via `POST /knowledge-base/documents`; all confirmed `status: ready`. (The KB also already held 4 SOPs from earlier session work — SOP-001 through SOP-004 — left in place; both sets are real, legitimate synthetic content.)
- **Workflow A images:** `workflow_a/clean_inspection_report.png` (crisp synthetic report, Pump P-104 / SOP-100, bearing temperature 92°C — an escalation-worthy reading per SOP-100 §3) and `workflow_a/degraded_inspection_report.png` (same content, deliberately degraded: small low-contrast text block, noise, slight rotation). Regenerable via `generate_workflow_a_images.py`. Verified against the real OCR pipeline before use: clean → `mean_confidence=0.995`, no escalation; degraded → `mean_confidence=0.909`, `completeness_estimate=0.49` (< the 0.6 threshold) → escalates, with **zero crashes** — tuning this asset surfaced (and required backing off from) a real edge-case crash in `backend/domain/document_processing/ocr.py`'s `_parse_predict_mapping` when PaddleOCR detects literally zero regions (`ValueError: The truth value of an empty array is ambiguous`); noted here as a minor finding, not filed as a blocking regression since the shipped asset avoids it.
- **Workflow B tasks:** `workflow_b_tasks.py` — `CLEAN_TASK` (pump hydraulic power calculation, deterministic expected output 36.11 kW) and `TRICKY_TASK` (pipe diameter + Reynolds-number classification, deterministic expected output `0.1784` / `turbulent`). Both tasks embed their input values as literals in the prompt rather than expecting stdin, because `execute_code`'s schema (`backend/models/schemas.py ExecuteCodeInput`) has no stdin/argv channel — only `code`, `language`, `input_files`.
- **Harness:** `backend/tests/test_sih_workflows.py`, integration-tier (`@pytest.mark.integration`, gated behind `BULWARK_E2E_KB_SEEDED=1`), hits the real app/DB the same way `test_e2e_workflow.py`'s existing integration test does.

## How this was run

```bash
ollama serve                                    # already running with qwen3.5:9b, qwen2.5-coder:7b, qwen3-embedding:0.6b pulled
PYTHONPATH=. uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 3 synthetic SOPs ingested via POST /api/v1/knowledge-base/documents, confirmed ready
cd backend && BULWARK_E2E_KB_SEEDED=1 PYTHONPATH=.. .venv/bin/python -m pytest tests/test_sih_workflows.py -v -s
```

Wall-clock: 17m29s for 20 real jobs (5×A-clean + 1×A-degraded + 5×B-clean + 3×B-tricky + 1×B-network-check + 5×C-covered + 1×C-uncovered).

## Results table

| Workflow | Runs | Termination | Task success | Notes |
|---|---|---|---|---|
| **A — scan → SOP retrieval → findings → DOCX** (clean asset) | 5 | 100% (5/5) | **20% (1/5)** — below 80% threshold | See Regression 1 |
| A — degraded asset (escalation demo) | 1 | 100% | escalation *functionally* succeeded (real vision-model transcription, correct uncertainty framing not separately re-checked) but **not visible in the trace** | See Regression 2 |
| **B — coding → generation → sandbox execution** (clean task) | 5 | 100% (5/5) | 100% (5/5) | generate_code/execute_code both appear as distinct audited steps every run |
| B — tricky task (correction-loop demo) | 3 | 100% (3/3) | n/a (demo, not part of the ≥5 count) | Correction loop observed in **0/3** — qwen2.5-coder:7b solved the tricky variant correctly on the first attempt every time; the task didn't induce a bug (see "Open items") |
| B — no-network/no-install check | 1 | 100% | pass | No `pip install`, no network-error strings in sandbox stdout/stderr |
| **C — local knowledge query → grounded answer** (covered question) | 5 | 100% (5/5) | 100% (5/5) | `search_knowledge_base` explicit in trace every run |
| C — uncovered question (C2, honest no-grounding) | 1 | 100% | pass | Retrieval still explicit; answer: *"The local knowledge base contains no entries regarding recommended tire pressure for forklifts operating in the loading bay."* — no fabricated SOP citation |
| **D — sovereignty proof** | — | — | pass (qualitative) | `GET /api/v1/network-status` was live throughout this entire session (network_monitor running continuously per Task 18); not separately re-verified here beyond confirming the monitor process was up — full retroactive audit query is Task 18's `scripts/audit_egress_report.py`, not re-run as part of this task |

**Aggregate thresholds (`docs/testing.md`):** correct termination — **met, 100% across all 20 jobs**. Task success ≥80% per workflow — **met for B and C; FAILED for A (20%)**. Structured-output validity ≥95% — **met where a DOCX was actually attempted (4/4 attempts were schema-valid, i.e. 100% of attempts)**, but this doesn't rescue A's success rate since 3 of those valid DOCX-producing runs skipped the required retrieval step.

## Regression 1 — Orchestrator does not reliably follow Workflow A's required capability sequencing

**Severity: blocking against the 80% threshold. Filed against Task 10 (Orchestrator) and flagged for Task 20 (Orchestrator model benchmark/decision).**

`docs/demo.md` Workflow A requires `extract_document` → `search_knowledge_base` → `create_docx`, in that order, every time ("not skipped or reordered" is an explicit success criterion). Across 5 identical runs (same clean asset, same message) with `qwen3.5:9b` as the reasoning model:

| Run | job_id | Capability sequence | Outcome |
|---|---|---|---|
| 1 | `d14277ef-6cc2-4f4a-a934-3118117e0f53` | `extract_document → create_docx` | Skipped retrieval; DOCX produced, no fabricated SOP citation in the final message — just no grounding step at all |
| 2 | `17dd1748-fb99-46cd-bce2-19ee37440940` | `extract_document → create_docx` | Same as run 1 |
| 3 | `ad37a316-b97a-4e00-bf0a-1ed61fa60c99` | `extract_document → search_knowledge_base → create_docx` | **Correct** — the only fully-compliant run |
| 4 | `af109289-c0db-4ca6-89b4-e285f8897e92` | `extract_document → search_knowledge_base` | Retrieval happened, but the model then refused to draft an approval note at all — its final message reasoned (defensibly, on safety grounds) that a 92°C bearing reading exceeds SOP limits and "the unit cannot be returned to service... approval for release is denied." No DOCX. |
| 5 | `b96ae339-1d48-4e03-9816-9615efe59e22` | `extract_document → create_docx` | Same as runs 1/2 |

Reading across all 5: the model reliably calls `extract_document` first, and reliably ends the job correctly (no hangs, no malformed output, no crash — termination is 100%). What's unreliable is whether it bothers to call `search_knowledge_base` before drafting findings/deciding — 3 of 5 times it skipped straight to drafting (or refusing to draft) without grounding the decision in the SOP content at all. Run 4 is a genuinely interesting edge case: the model's *judgment* (don't approve release of unsafe equipment) is arguably correct and safety-conscious, but it directly conflicts with the literal success criterion (produce a DOCX every time) and with `docs/demo.md`'s scripted demo expectation.

**This is exactly the kind of finding Task 20's Orchestrator benchmark (`qwen3.5:9b` vs `gpt-oss:20b`) exists to catch** — task success rate below the 80% bar on a real demo workflow is one of the documented hard thresholds that decides whether the smaller model is retained. Recommend Task 20 treat this Workflow A result as a concrete, reproducible data point (not just its own fresh battery) when applying the decision rule.

## Regression 2 — vision escalation's `model_invoked` audit event is orphaned from its Job

**Severity: real, precisely diagnosed, one-line root cause. Filed against Task 11 (OCR/document processing).**

The degraded-asset run (`job_id 2dbb70e9-2e53-4ca6-b916-061ce335ec30`) genuinely triggered vision escalation — `tool_result: extract_document`'s payload shows `"extraction_method": "vision_escalation"` and `"warnings": ["Escalation triggered: completeness_below (0.49 < 0.6)"]`, and the transcribed text differs from the source in a way characteristic of a real vision-model read (misread date), not deterministic OCR. But no `model_invoked` event with `resource_type: vision` appears anywhere in that job's `/trace` — which broke this harness's assertion and would equally break the live demo's trace panel for exactly the moment `docs/demo.md` calls out as worth showing judges.

**Root cause, confirmed by querying `audit_events` directly (bypassing the job-scoped API):** the vision `model_invoked` event *was* written to the database — with `job_id: NULL` instead of the real job's id:

```
job_id=None  2026-09-14T13:50:36.359267+00:00  {"resource_type":"vision","model_identifier":"qwen3.5:9b","prompt_tokens":2139,"completion_tokens":178,"duration_ms":22683}
```

`backend/domain/document_processing/pipeline.py::process_document(document_id, image_path, job_id: Optional[str] = None)` accepts and correctly threads `job_id` down into `_process_one_image` → `escalate_to_vision` → `model_runtime.generate(resource_type="vision", ..., job_id=job_id)`. But its only caller, `backend/domain/capabilities/extract_document.py:110`, calls it as:

```python
result = await process_document(document_id, str(file_path))
```

— omitting `job_id` entirely, so it silently defaults to `None` for *every* extract_document invocation that escalates to vision, not just this one. The event is real and not lost from the database (Task 18's retroactive audit report would still count it), but it is invisible to `GET /api/v1/jobs/{job_id}/trace` and therefore to the live trace UI — undermining exactly the "intermediate results, visible in the trace" success criterion `docs/demo.md` states for Workflow A's escalation path.

**Not fixed here** (Task 19 is validation-only; the fix is a one-line change to pass `job_id` at `extract_document.py:110`, which belongs to Task 11's owner).

## Open items / lower-severity notes

- **B-tricky's correction loop didn't trigger in 3/3 runs** — `qwen2.5-coder:7b` solved the deliberately-tricky pipe-diameter/Reynolds-number task correctly on the first attempt every time. Not a bug — a data point that this model is more capable at this class of industrial calculation than the asset assumed. If a correction-loop demo is wanted for the actual SIH presentation, either rehearse with a harder task or accept showing the clean path only; forcing a bug via a deliberately-malformed prompt is a copy change, not a code change, and can be revisited without touching application code.
- **The OCR-pipeline crash on zero detected regions** (found while tuning the degraded asset, described above) is a real edge case worth Task 11's owner being aware of, even though it didn't block this task — an even-more-degraded real-world scan than this asset could hit it live during a demo.
- Workflow D was not independently re-validated beyond confirming the monitor was live throughout; Task 18's own scripts (`scripts/audit_egress_report.py`) are the authoritative Workflow D proof and weren't re-run here to avoid duplicating that task's job.
- No application code was changed by this task, per its own scope; both regressions above are documented with exact repro (job IDs, timestamps, root cause) for their owning tasks rather than patched here.

## Acceptance checklist (tasks/19-sih-workflow-validation.md §9)

- [x] Representative assets exist: clean + degraded report images; realistic synthetic SOPs ingested to `ready`; a clean + a buggy(-attempted) coding task.
- [x] Each of the four workflows run ≥5× (or, for D, continuously observed) against `docs/demo.md` criteria.
- [ ] **Workflow A:** sequencing correct only 1/5 runs — **fails** the "not skipped or reordered every run" criterion. Regression 1 filed.
- [x] **Workflow B:** generation/execution distinct every run; termination correct; no network/package-install attempts. Correction-loop demonstration attempted (not observed in 3 runs — noted, not a blocking failure of this task).
- [x] **Workflow C:** retrieval explicit every run; grounded answers; uncovered-question case (C2) returns an honest no-grounding answer.
- [~] **Workflow D:** live panel confirmed up; full retroactive audit cross-check deferred to Task 18's own scripts (not duplicated here).
- [ ] Hard thresholds met across the runs — **task success ≥80% per workflow fails for Workflow A (20%)**; termination 100% and B/C ≥80% hold.
- [x] Results table recorded in this log; two regressions filed with owning tasks and concrete repro.
- [x] No application code changed; no workflows beyond the four added; no invented thresholds.
- [ ] `git diff` reviewed; branch pushed; PR prepared — pending final review pass.
