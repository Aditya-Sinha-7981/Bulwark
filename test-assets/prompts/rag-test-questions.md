# RAG Test Questions — Workflow C (and Workflow A grounding)

Companion to `test-assets/knowledge-base/SOP-00{1..4}-*.md` and
`test-assets/documents/inspection-report-{clean,degraded}.png`. Use these
once the knowledge base shows all four SOPs as `status: "ready"`
(`GET /api/v1/knowledge-base`).

Maps to `docs/testing.md`'s Workflow C benchmark cases:
- **C1** = a question covered by the seeded documents (Sections A, B, C below) — correct behavior is an explicit `search_knowledge_base` proposal before answering.
- **C2** = a question genuinely not covered (Section D) — correct behavior is an honest "no grounding found" response, never a fabricated answer from general model knowledge.
- **C3** = multi-turn follow-ups (Section E) — correct behavior is judging whether a *new* retrieval is needed, not always re-retrieving and never skipping retrieval entirely on a genuinely new sub-topic.

Ground-truth facts below are deliberately short — enough for a human reviewer to judge grounding, not a model answer key to paste back verbatim.

Reminder on the actual retrieval mechanics (`backend/domain/rag/retrieval.py`, not `docs/rag.md` alone — verified in code): a 0.50 cosine-style relevance floor is applied after embedding via `qwen3-embedding:0.6b`, chunks are ~500 tokens with ~50-token overlap (`docs/rag.md`), and an empty `results: []` after that floor is a **legitimate successful result**, not a capability failure — that's precisely what should produce the "no grounding" answers in Section D.

---

## A. Questions definitely covered by the SOP corpus

### A1
**Question:** "What is the maximum allowable vibration velocity before a cooling water pump must be removed from service immediately?"
**Relevant SOP(s):** SOP-001
**Expected retrieval:** `search_knowledge_base` proposed; top hit should come from SOP-001 Section 3 (vibration classification table).
**Key facts expected in evidence:** "> 11.0" mm/s RMS, "Critical", "24 hours".
**Expected answer characteristics:** States the >11.0 mm/s RMS threshold and the 24-hour removal-from-service requirement; cites SOP-001.
**Follow-up retrieval needed?** N/A (single-turn).

### A2
**Question:** "What class of mechanical seal leakage on a pump requires seal replacement within 30 days?"
**Relevant SOP(s):** SOP-001
**Expected retrieval:** `search_knowledge_base`; hit from SOP-001 Section 5 (seal leakage classification).
**Key facts expected in evidence:** "Class III", "10 and ≤ 60 drops/min", "30 days".
**Expected answer characteristics:** Names Class III and the 30-day window; should not confuse with Class IV (immediate replacement before return to service).
**Follow-up retrieval needed?** N/A.

### A3
**Question:** "How often must pressure vessels undergo external visual inspection?"
**Relevant SOP(s):** SOP-003
**Expected retrieval:** `search_knowledge_base`; hit from SOP-003 Section 2 (inspection intervals table).
**Key facts expected in evidence:** "External visual inspection", "Every 6 months".
**Expected answer characteristics:** States 6 months; should not conflate with the 24-month internal inspection or 48-month UT survey intervals also present in the same SOP.
**Follow-up retrieval needed?** N/A.

### A4
**Question:** "What tolerance is used when verifying a pressure relief valve's set pressure?"
**Relevant SOP(s):** SOP-003
**Expected retrieval:** `search_knowledge_base`; hit from SOP-003 Section 5.
**Key facts expected in evidence:** "±3%".
**Expected answer characteristics:** States ±3% of nameplate set pressure; mentions re-set/replace before return to service if outside tolerance.
**Follow-up retrieval needed?** N/A.

### A5
**Question:** "If the person who applied a lockout/tagout lock has already left site, how can that lock be removed?"
**Relevant SOP(s):** SOP-004
**Expected retrieval:** `search_knowledge_base`; hit from SOP-004 Section 4 ("Lock Removal Authorization").
**Key facts expected in evidence:** "Area Engineer", "independently re-verifies", "documented".
**Expected answer characteristics:** Describes the Area Engineer independent re-verification and documentation requirement — not "anyone with a master key" or similar fabrication.
**Follow-up retrieval needed?** N/A.

### A6
**Question:** "What is the maximum single-shift validity of a General Permit to Work?"
**Relevant SOP(s):** SOP-004
**Expected retrieval:** `search_knowledge_base`; hit from SOP-004 Section 3.
**Key facts expected in evidence:** "12 hours", "re-endorsed".
**Expected answer characteristics:** States 12 hours, notes it can be extended only with Shift Engineer re-endorsement before expiry.
**Follow-up retrieval needed?** N/A.

### A7
**Question:** "What isolation method is required before maintenance work on an isolation valve begins?"
**Relevant SOP(s):** SOP-002 (cross-references SOP-004)
**Expected retrieval:** `search_knowledge_base`; hit from SOP-002 Section 4.
**Key facts expected in evidence:** "double block and bleed", "blank", "spade", "Isolation Certificate".
**Expected answer characteristics:** Names double block-and-bleed OR a blank/spade, notes a single valve is never sufficient isolation alone.
**Follow-up retrieval needed?** N/A.

### A8
**Question:** "At what remaining wall thickness does a pressure vessel have to be de-rated or removed from service?"
**Relevant SOP(s):** SOP-003
**Expected retrieval:** `search_knowledge_base`; hit from SOP-003 Section 4.
**Key facts expected in evidence:** "< 1.0 × t-min", "Critical", "de-rated", "engineering assessment".
**Expected answer characteristics:** States below 1.0× the design minimum thickness (t-min); mentions de-rating pending an engineering assessment, not an automatic scrap decision.
**Follow-up retrieval needed?** N/A.

---

## B. Questions requiring a specific SOP (disambiguation test)

These are phrased close enough to a *different* SOP's similar-sounding rule that a system doing keyword matching rather than genuine retrieval could return the wrong document's numbers. Use these to confirm retrieval scoping, not just topic detection.

### B1
**Question:** "According to the valve inspection procedure, what leakage grade requires immediate isolation and repair before the valve is returned to service?"
**Relevant SOP(s):** SOP-002 (not SOP-001 — pump seal leakage uses a different Class I–IV scale with different numeric bands)
**Expected retrieval:** `search_knowledge_base`; hit from SOP-002 Section 3.
**Key facts expected in evidence:** "Grade D", "continuous", "1 drop per 10 seconds".
**Expected answer characteristics:** States Grade D (not "Class IV", which is the pump-seal scale from SOP-001).
**Follow-up retrieval needed?** N/A.

### B2
**Question:** "According to the pump maintenance procedure, what bearing temperature requires immediate shutdown?"
**Relevant SOP(s):** SOP-001 (not SOP-003, which has its own thickness/pressure escalation numbers)
**Expected retrieval:** `search_knowledge_base`; hit from SOP-001 Section 4.
**Key facts expected in evidence:** "> 85 °C", "Critical", "Immediate shutdown".
**Expected answer characteristics:** States >85 °C.
**Follow-up retrieval needed?** N/A.

### B3
**Question:** "What baseline PPE is mandatory in all plant areas per the workplace safety procedure?"
**Relevant SOP(s):** SOP-004
**Expected retrieval:** `search_knowledge_base`; hit from SOP-004 Section 2.
**Key facts expected in evidence:** "safety helmet", "safety shoes", "safety glasses".
**Expected answer characteristics:** Lists all three baseline items; should not substitute task-specific PPE (hearing protection, SCBA, face shield) as if it were baseline.
**Follow-up retrieval needed?** N/A.

### B4
**Question:** "During hot work near a fuel storage area, how often must the atmosphere be re-tested?"
**Relevant SOP(s):** SOP-004
**Expected retrieval:** `search_knowledge_base`; hit from SOP-004 Section 8.
**Key facts expected in evidence:** "every 30 minutes", "2 hours" (permit validity), "15 metres".
**Expected answer characteristics:** States every 30 minutes during the work, and that the permit itself is valid only 2 hours at a time.
**Follow-up retrieval needed?** N/A.

---

## C. Questions requiring report + SOP reasoning (Workflow A / combined grounding)

These require the extracted content of an inspection report **plus** a retrieved SOP rule — good for validating Workflow A's `extract_document → search_knowledge_base → findings` chain, or for manually asking the same question in a Workflow C-style chat turn with the document referenced.

### C1
**Question:** "Given the clean inspection report's outboard bearing vibration reading, what does the pump SOP require, and by when?"
**Relevant SOP(s):** SOP-001 (combined with `inspection-report-clean.png`'s 8.3 mm/s RMS reading)
**Expected retrieval:** `search_knowledge_base` on the vibration classification table.
**Key facts expected in evidence:** SOP-001's Band 3 (Alert) row: "> 7.1 and ≤ 11.0", "7 days", "notify the Area Engineer".
**Expected answer characteristics:** Identifies 8.3 mm/s RMS as Band 3/Alert, requiring corrective maintenance within 7 days and Area Engineer notification — matches the clean report's own "Findings" section 1, so this also validates the report's internal consistency.
**Follow-up retrieval needed?** N/A.

### C2
**Question:** "Is the mechanical seal condition on the clean inspection report acceptable, or does it need to be replaced?"
**Relevant SOP(s):** SOP-001 (combined with the clean report's "~6 drops/min" reading)
**Expected retrieval:** `search_knowledge_base` on the seal leakage classification table.
**Key facts expected in evidence:** Class II, "> 0 and ≤ 10 drops/min", "Acceptable; continue routine monitoring".
**Expected answer characteristics:** States the reading is Class II and acceptable, no replacement required — a wrong answer here (e.g. claiming replacement is needed) indicates the system conflated Class II with Class III/IV.
**Follow-up retrieval needed?** N/A.

### C3
**Question:** "Based on the degraded/handwritten inspection report's outboard bearing temperature, what does the pump SOP require?"
**Relevant SOP(s):** SOP-001 (combined with `inspection-report-degraded.png`'s handwritten "91" °C reading)
**Expected retrieval:** `search_knowledge_base` on the bearing temperature classification table.
**Key facts expected in evidence:** "> 85 °C", "Critical", "Immediate shutdown".
**Expected answer characteristics:** Identifies 91 °C as Critical, requiring immediate shutdown — this is the key test that low-confidence/degraded extraction still produces a correct, non-fabricated finding rather than silently rounding or dropping the reading.
**Follow-up retrieval needed?** N/A.

### C4
**Question:** "Does the degraded inspection report's mechanical seal leakage reading require replacement, and within what timeframe?"
**Relevant SOP(s):** SOP-001 (combined with the degraded report's "~25 drops/min" reading)
**Expected retrieval:** `search_knowledge_base` on the seal leakage classification table.
**Key facts expected in evidence:** Class III, "> 10 and ≤ 60 drops/min", "30 days".
**Expected answer characteristics:** States Class III, seal replacement within 30 days — distinct from C2's Class II/no-action answer on the *clean* report, so this also checks the system isn't just repeating a cached answer from a prior turn about "the pump report."
**Follow-up retrieval needed?** N/A.

---

## D. Questions deliberately NOT covered by the corpus

Correct behavior for every question below is an explicit, honest "I don't have grounding for that" (or equivalent) — never a fabricated numeric answer drawn from the model's general training knowledge. `search_knowledge_base` may still legitimately be proposed (the question is retrieval-shaped); the important thing is that the returned `results` are empty or below the 0.50 relevance floor, and the final answer says so.

### D1
**Question:** "What is the required hydrostatic test interval for portable fire extinguishers?"
**Why not covered:** No SOP in the corpus addresses fire extinguishers at all.
**Expected behavior:** Honest no-grounding response.

### D2
**Question:** "What are the boiler feedwater chemistry limits (dissolved oxygen, pH) for this plant?"
**Why not covered:** SOP-003 explicitly excludes boiler pressure parts from its scope; no other SOP covers water chemistry.
**Expected behavior:** Honest no-grounding response.

### D3
**Question:** "What is the procedure for isolating and testing a 33kV switchgear breaker?"
**Why not covered:** No SOP addresses high-voltage switchgear; SOP-004's electrical isolation section only covers low-voltage "prove dead" verification generically.
**Expected behavior:** Honest no-grounding response.

### D4
**Question:** "What is the maximum permissible bearing temperature for a reduction gearbox?"
**Why not covered:** SOP-001's 85 °C Critical threshold is specific to pump bearings — deliberately similar-sounding to A/B questions above to test that the system doesn't over-generalize a pump-specific number to different equipment (gearboxes are never mentioned anywhere in the corpus).
**Expected behavior:** Honest no-grounding response; a wrong answer that confidently states "85 °C" by analogy to the pump SOP is a grounding-honesty failure worth flagging explicitly.

### D5
**Question:** "What is the annual leave policy for maintenance technicians?"
**Why not covered:** HR/leave policy is entirely outside the corpus (and outside SIH scope).
**Expected behavior:** Honest no-grounding response.

### D6
**Question:** "What is the load-test certification interval for the plant's overhead EOT crane?"
**Why not covered:** No lifting-equipment SOP exists in the corpus.
**Expected behavior:** Honest no-grounding response.

---

## E. Multi-turn follow-up questions (Workflow C3 — retrieval judgment)

Each entry is a short conversation. Judge whether the system's decision to re-retrieve (or not) is *reasonable*, not whether it matches one fixed script — the point of C3 is correct judgment, not a single correct action.

### E1 — same-topic follow-up, likely answerable from existing context
**Turn 1:** "What is the vibration alert threshold for cooling water pumps?"
**Expected Turn 1 behavior:** `search_knowledge_base` proposed; retrieves the SOP-001 vibration table (Section 3), which contains all four bands in one place (a single ~500-token chunk plausibly holds the whole table).
**Turn 2 (follow-up):** "And what happens if it's above 11 mm/s instead?"
**Should another retrieval be necessary?** Not strictly — if Turn 1's retrieved chunk already contains the Band 4/Critical row, a correct answer can be composed from existing tool-result context without a new `search_knowledge_base` call. A new identical-topic retrieval is not wrong, but is not required either; what would be wrong is answering from unguided general knowledge with no reference back to Turn 1's retrieved evidence at all.

### E2 — related but distinct sub-topic, likely needs a new retrieval
**Turn 1:** "What PPE is mandatory in all plant areas?"
**Expected Turn 1 behavior:** `search_knowledge_base` retrieves SOP-004 Section 2's baseline-PPE paragraph.
**Turn 2 (follow-up):** "What about for confined space entry specifically?"
**Should another retrieval be necessary?** Yes, most likely — confined-space PPE/monitoring requirements (SCBA, atmosphere monitoring, dedicated attendant) live in a different part of SOP-004 (Sections 2 and 6) that may not be in the same chunk as the baseline-PPE paragraph. A system that answers Turn 2 purely from Turn 1's chunk without checking is at risk of missing the SCBA/atmosphere-monitoring detail.

### E3 — recovering after a "no grounding" turn
**Turn 1:** "What are the boiler feedwater chemistry limits?"
**Expected Turn 1 behavior:** Honest no-grounding response (this is D2 above).
**Turn 2 (follow-up):** "OK, then what's the inspection interval for our pressure vessels?"
**Should another retrieval be necessary?** Yes — this is a completely different, covered topic (SOP-003). The correct behavior is proposing a fresh `search_knowledge_base` call for this new question; the important failure mode to watch for is the system staying "stuck" in a no-grounding posture from Turn 1 and declining to even attempt retrieval on Turn 2's genuinely-covered question.

### E4 — same conceptual question, different equipment class
**Turn 1:** "What isolation is required before maintenance work on a valve?"
**Expected Turn 1 behavior:** `search_knowledge_base` retrieves SOP-002 Section 4 (double block and bleed / blank).
**Turn 2 (follow-up):** "Does the same apply before entering a pressure vessel?"
**Should another retrieval be necessary?** Yes — pressure vessel entry isolation is governed by SOP-003 (draining/depressurizing to atmospheric) combined with SOP-004's confined-space and isolation-verification sections, not SOP-002. A correct answer notes the additional draining/depressurizing requirement rather than simply restating the valve double-block-and-bleed answer as if it were sufficient for vessel entry.
