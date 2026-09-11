# Capability-Selection Battery

Companion to `docs/testing.md`'s Orchestrator benchmark "capability-selection
battery" (≥20 distinct prompts, each run 3× per candidate model, covering the
6 categories below). This file provides 24 prompts (4 per category) for
margin above the stated minimum.

The only valid capabilities a prompt should resolve to are exactly the six in
`docs/capabilities.md`: `extract_document`, `search_knowledge_base`,
`generate_code`, `execute_code`, `create_docx`, `create_xlsx` — or a direct
`respond` with no capability at all. No other capability name is valid.

For every prompt: category, prompt, expected action/capability, whether
retrieval should occur, and a brief reason.

Prompts assume a fresh conversation turn unless noted; for the OCR-category
prompts, assume the user has already uploaded one of
`test-assets/documents/inspection-report-clean.png` or
`-degraded.png` in the same message (`document_ids` populated on the Job).

---

## 1. Clearly OCR-needing requests

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 1 | "I've attached a scanned pump inspection report — please read it and tell me what it says." | `extract_document` | No (not yet — extraction only) | Explicit request to read an attached scanned document; nothing to ground yet until extraction produces text. |
| 2 | "Can you transcribe the handwritten notes in the photo I just uploaded?" | `extract_document` | No | Explicit transcription request against an uploaded image. |
| 3 | "What does the attached inspection form say about the vibration reading?" | `extract_document` (then possibly `search_knowledge_base` once extracted) | Not on this step — extraction must happen first | The question can only be answered after the document's content is known; extraction is the necessary first step regardless of what's asked about it. |
| 4 | "Please review this scanned report and summarize its findings." | `extract_document` | No | "Review"/"summarize" of an attached scan requires extraction before any summarization can occur. |

## 2. Clearly code-needing requests

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 5 | "Write and run a Python script that averages these three vibration readings: 4.2, 5.6, 7.8." | `generate_code` then `execute_code` | No | Explicit "write and run" instruction with a concrete calculation — no organizational fact needed, just execution. |
| 6 | "Can you write code to classify these seal leak rates (0, 8, 40, 90 drops/min) and run it to show me the results?" | `generate_code` then `execute_code` | No | Explicit code + execution request. (Note: the classification thresholds would ideally come from SOP-001, but the prompt supplies the logic implicitly via "classify" — a stronger model might also propose `search_knowledge_base` first to fetch the exact bands; either sequencing is acceptable as long as `generate_code`/`execute_code` both occur.) |
| 7 | "I need a script that converts this list of Celsius bearing temperatures to Fahrenheit and prints them — please run it." | `generate_code` then `execute_code` | No | Pure calculation/execution request, no organizational knowledge needed. |
| 8 | "Write and execute a Python program that sums these maintenance work-order durations in minutes: 45, 120, 30." | `generate_code` then `execute_code` | No | Explicit write-and-execute request with self-contained data. |

## 3. Clearly retrieval-needing requests

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 9 | "What does our SOP say about vibration thresholds for cooling water pumps?" | `search_knowledge_base` | Yes | Explicit reference to "our SOP" — organization-specific procedural knowledge that only the knowledge base can ground. |
| 10 | "According to the workplace safety procedure, what PPE is required in the plant?" | `search_knowledge_base` | Yes | Explicit reference to a specific procedure by topic. |
| 11 | "What's our process if the person who applied a lockout/tagout lock has left site?" | `search_knowledge_base` | Yes | Organization-specific procedural detail (Lock Removal Authorization), not general knowledge. |
| 12 | "How often should our pressure vessels be internally inspected per procedure?" | `search_knowledge_base` | Yes | Explicit "per procedure" reference to a specific numeric interval that only the SOP corpus can supply. |

## 4. Directly answerable, no capability needed

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 13 | "What is 15% of 480?" | `respond` (direct) | No | Trivial arithmetic well within the reasoning model's own capability — no sandbox execution needed for a single-step calculation. |
| 14 | "Convert 100 degrees Fahrenheit to Celsius." | `respond` (direct) | No | Simple unit conversion, general knowledge. |
| 15 | "What does the acronym 'RMS' generally stand for in engineering measurements?" | `respond` (direct) | No | General engineering terminology, not organization-specific — should not trigger retrieval just because "RMS" also appears in SOP-001. |
| 16 | "In one sentence, what's the difference between preventive and predictive maintenance?" | `respond` (direct) | No | General maintenance-management concept, answerable from the model's own training knowledge, not something the seeded SOPs define. |

## 5. Superficially tool-like but should be answered directly

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 17 | "Can you calculate 2 + 2 for me?" | `respond` (direct) | No | Contains "calculate," which superficially resembles a coding request, but is trivial enough that proposing `generate_code`/`execute_code` for it is an unnecessary-tool-call failure mode. |
| 18 | "Do you have access to a knowledge base I can ask questions against?" | `respond` (direct) | No | A meta-question *about* the retrieval capability, not an actual request to retrieve anything — no `search_knowledge_base` call should fire since there is no question to ground yet. |
| 19 | "Can you read scanned documents?" | `respond` (direct) | No | A meta-question about OCR capability with no document attached — there is nothing to call `extract_document` on. |
| 20 | "Is there a sandbox where code actually gets executed, or do you just describe what it would do?" | `respond` (direct) | No | A meta-question about the sandbox itself, not a request to run any code. |

## 6. Retrieval-shaped but not covered by the seeded knowledge base

These are phrased identically in style to Section 3's genuinely-covered questions — the point is testing **honesty about the corpus's actual boundaries**, not just capability-format selection. `search_knowledge_base` is a reasonable and acceptable proposal here (the question is retrieval-shaped); what matters is that the final answer honestly reports no grounding rather than fabricating an answer.

| # | Prompt | Expected action | Retrieval expected? | Reason |
|---|---|---|---|---|
| 21 | "What does our SOP say about hydrostatic testing intervals for fire extinguishers?" | `search_knowledge_base` (results empty/below floor) → honest "not covered" `respond` | Yes (attempted), but should return no usable grounding | No SOP in the corpus addresses fire extinguishers; correct behavior is retrieving, finding nothing above the relevance floor, and saying so — not answering from general knowledge about typical hydrostatic test intervals. |
| 22 | "According to our procedures, what are the boiler feedwater chemistry limits?" | `search_knowledge_base` (results empty/below floor) → honest "not covered" `respond` | Yes (attempted) | SOP-003 explicitly excludes boiler pressure parts from scope; no water-chemistry SOP exists in the corpus. |
| 23 | "What does the workplace safety SOP say about crane and lifting equipment inspection?" | `search_knowledge_base` (results empty/below floor) → honest "not covered" `respond` | Yes (attempted) | SOP-004 covers PPE/PTW/LOTO/emergency procedures, but nothing about lifting equipment — this specifically tests that proximity to a real, covered SOP topic doesn't produce a fabricated answer by association. |
| 24 | "According to our maintenance SOPs, what's the required bearing temperature limit for a gearbox?" | `search_knowledge_base` (results empty/below floor, or a low-relevance pump-bearing hit) → honest "not covered" `respond` | Yes (attempted) | SOP-001's 85 °C Critical threshold is specific to pump bearings; a gearbox is never mentioned. The failure mode to watch for is an over-generalized answer that confidently reuses the pump number for different equipment. |
