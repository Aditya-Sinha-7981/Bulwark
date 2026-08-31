# Testing

## Test categories

| Category | Covers |
|---|---|
| Unit tests | Policy engine rules, capability input/output schema validation, artifact renderers, Lifecycle Manager eviction logic — all pure/isolated logic in `domain/` |
| Integration tests | Capability Executors against real (local) dependencies — Ollama, Chroma, Docker, PaddleOCR |
| Capability contract tests | Every capability in `capabilities.md` — valid input produces schema-valid output; invalid input is rejected before execution |
| API tests | Every endpoint in `api.md` — request/response shape, status codes, error format |
| Agent tests | The Orchestrator loop against representative conversations — proposal parsing, malformed-output handling, step-limit enforcement, termination |
| Model tests | The Orchestrator benchmark (below) |
| OCR tests | `document-processing.md`'s tiering — confirm escalation triggers correctly per signal, not just on one confidence number |
| RAG tests | Ingestion → retrieval round-trip against seeded synthetic documents; empty-result honesty (no hallucinated grounding) |
| Sandbox tests | `execute_code` against known-good, known-failing, and known-timeout scripts; network-denial verification (attempt an outbound call inside the sandbox, confirm it fails) |
| Security tests | Policy denial paths, filesystem-scope enforcement, network-access invariant |
| Zero-egress tests | Full offline run (`deployment.md`'s checklist); connection-monitor accuracy |
| Artifact tests | Schema validation, atomic-write behavior, malformed-payload rejection |
| Frontend tests | SSE handling, trace rendering, API integration — component-level, no exhaustive e2e UI suite required for SIH |
| End-to-end SIH workflow tests | The four demo workflows, run in full (`demo.md`) |
| Performance/memory tests | The M4 Pro memory test (below) |

## Failure injection

Explicitly test each of these, not just the happy path:

- Malformed model output (Orchestrator proposal doesn't parse) — confirm the one free corrective turn, then step-limit counting, per `agent.md`
- OCR failure (corrupt file) — confirm a clean failed result, not a crash
- Model unavailable (Ollama down) — confirm a failed capability result, not a hung request
- Model load failure (bad model name, out of memory) — confirm `error` audit event, Job continues in failed state, not a crash
- Sandbox timeout — confirm hard kill at the configured timeout, `timed_out: true` in the result
- Sandbox crash — confirm captured non-zero exit / stderr, not an unhandled exception
- Policy denial — confirm the Orchestrator receives a clear denial reason and doesn't loop retrying the identical call
- Corrupted artifact write — confirm atomic-write behavior means no broken file is ever linked from a successful `Artifact` row
- Missing RAG evidence (empty knowledge base or no relevant results) — confirm an honest "no grounding" response, not fabrication
- Resource exhaustion (memory pressure during a load) — confirm eviction triggers per `models.md`, not an OOM crash

## Orchestrator benchmark — exact procedure

**Cannot be executed from outside the actual M4 Pro — this is the procedure to run, not a report of results already obtained.**

### Candidates

- **A:** `qwen3.5:9b` (current default)
- **B:** `gpt-oss:20b` (fallback candidate)

### Test suite

**Capability-selection battery** (≥20 distinct prompts, each run 3× per candidate):
1. Clearly OCR-needing request
2. Clearly code-needing request
3. Clearly retrieval-needing request
4. Directly answerable, no capability needed
5. Superficially tool-like but actually answerable directly
6. Retrieval-shaped but not covered by the seeded knowledge base (tests honesty, not just capability selection)

**Workflow A** (report → extraction → retrieval → findings → DOCX):
- A1: clean synthetic report — confirm `extract_document` proposed first
- A2: after extraction, confirm `search_knowledge_base` proposed before drafting findings
- A3: confirm findings payload validates against `create_docx`'s input schema with no stray prose
- A4: garbled extraction result — confirm no hallucinated confident findings; correct behavior flags insufficiency

**Workflow B** (code → generation → sandbox → verification):
- B1: working-code request — confirm `generate_code` → `execute_code` sequencing
- B2: confirm correct interpretation of a successful result and correct termination
- B3: inject a bug — confirm the model reads the error and issues a corrected `generate_code`, not a loop or silent failure
- B4: confirm no generated code attempts network calls or package installs

**Workflow C** (query → retrieval → grounded answer):
- C1: question covered by seeded documents — confirm explicit retrieval proposed
- C2: question not covered — confirm honest "no grounding" response
- C3: multi-turn follow-up — confirm correct judgment on whether new retrieval is needed

### Metrics

| Metric | Measured as |
|---|---|
| Capability selection accuracy | correct / total, from the battery |
| Malformed tool-call rate | invalid / total tool calls |
| Unnecessary tool-call rate | capability invoked when a direct answer was correct / total such cases |
| Missed required tool-call rate | direct answer given when a capability was required / total such cases |
| Correct tool arguments rate | schema+value-correct / total tool calls |
| Correct result interpretation | pass/fail, manually judged per step |
| Correct multi-step sequencing | pass/fail per workflow run |
| Correct termination | pass/fail per workflow run — must be 100% |
| Structured-output validity | schema-valid / total artifact-generation attempts |
| Task success rate | correct end-to-end deliverable / total runs (≥5 runs per workflow) |
| First-token latency | seconds, representative prompt |
| Tokens/sec | decode throughput, representative generation |
| Model load time | cold start to first response |
| Model unload time | time to free memory after `keep_alive` expiry |
| Practical peak memory | Activity Monitor / `ollama ps` at peak per workflow |

### Thresholds

| Metric | Threshold |
|---|---|
| Capability selection accuracy | ≥90% |
| Malformed tool-call rate | ≤5% |
| Unnecessary tool-call rate | ≤10% |
| Missed required tool-call rate | ≤5% |
| Correct tool arguments rate | ≥90% |
| Structured-output validity | ≥95% |
| Task success rate per workflow | ≥80% |
| Correct termination | 100% |

### Decision rule

- Select **A (`qwen3.5:9b`)** if it clears every threshold, or comes within ~5 points of B on task success rate while clearing all hard thresholds outright — its memory/latency advantage settles ties.
- Select **B (`gpt-oss:20b`)** if A fails any hard threshold, or its task success rate trails B by more than ~10–15 points.
- Escalate to `qwen3:14b` only if both fail — flag explicitly rather than silently substituting.

## M4 Pro memory test — exact procedure

1. **Absolute baseline** — fresh boot, OS only. Record memory (`vm_stat`/Activity Monitor).
2. **Realistic baseline** — browser (5–10 tabs), Spotify, VS Code, a terminal, running as they normally would be. Record memory — this is the real floor, not step 1.
3. **App-stack baseline** — backend, frontend dev server, Docker Desktop, Chroma/SQLite running. Record memory.
4. **Resource-loaded** — load each configured model via Ollama individually. Record memory and load time.
5. **Workflow-peak** — run a representative instance of each demo workflow with the reasoning model loaded, including whatever specialist-resource swap it triggers. Record peak memory.
6. **Concurrent-load case** — reasoning + code_generation resources loaded together (the case `models.md` estimates at ~14GB). Record actual peak memory here specifically, to validate or correct that estimate.
7. **Pressure check** — watch macOS memory-pressure indicator and `vm_stat` swap activity throughout. Any yellow/red or recorded swap is a fail regardless of whether it "technically fit."
8. **Latency-under-load check** — compare tokens/sec at step 6 against the idle-machine figure from the Orchestrator benchmark; flag >15–20% degradation as a finding.

**Acceptance criterion:** memory pressure stays green throughout, zero swap activity, ≥2–3GB genuine headroom remaining at peak.

## Reporting

Both benchmarks (Orchestrator, memory) should produce a short results table, not a formal report — enough to apply the decision rules above before Phase 4 implementation of the Orchestrator/Lifecycle Manager is fully committed to a specific model choice.
