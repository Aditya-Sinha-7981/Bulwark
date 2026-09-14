# Demo-Day Dry Run — Plain-Language Checklist

Use this the night before and again the morning of. It's not a developer test
plan — it's the exact sequence you'll actually show judges, so if it works
here, it'll work there. Companion to `full-stack-test-plan.md` (the detailed
engineering version) — this is the short one, for you.

---

## 0. Before you start

- [ ] Ollama running (`ollama serve`, or the menu-bar app)
- [ ] Docker Desktop running
- [ ] Backend running: `PYTHONPATH=. backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- [ ] Frontend running: `cd frontend && npm run dev`
- [ ] Open the app in the browser, check the bottom-left status indicator is
      green ("Local backend connected") — if it's not green, stop and fix
      that first, nothing else matters until it is

---

## 1. Workflow C — Ask a question (do this first, it's the safest one)

**What you'll say to judges:** "Let's ask it something from our internal
procedures."

**What to actually type in the chat:**
> What is the maximum allowable vibration velocity for a centrifugal pump
> before it needs a maintenance review?

**What should happen:**
- [ ] The trace panel shows a "search_knowledge_base" step happening — point
      at this, it's the proof the answer isn't made up
- [ ] The answer mentions a specific number/threshold, not a vague summary
- [ ] It comes back in a few seconds, not a minute+

**Bonus — the "honest AI" moment (do this once, it's a strong beat):**
> What's the recommended tire pressure for forklifts in the loading bay?

- [ ] It should say something like "I don't have that in the knowledge base"
      — **not** make something up. If it invents an answer, that's a real
      problem, tell me immediately.

---

## 2. Workflow A — Upload a report, get a Word doc back

**What you'll say to judges:** "Now let's give it a scanned report and have
it draft the paperwork."

**What to do:**
1. Attach `test-assets/documents/inspection-report-clean.png`
2. Type: *"Review this inspection report and draft an approval note."*

**What should happen, in order (watch the trace panel):**
- [ ] `extract_document` step (reads the image)
- [ ] `search_knowledge_base` step (checks the procedure) — **this is the
      step most likely to get skipped by the AI; if you don't see it, the
      run is not a good one to show, see "if something goes wrong" below**
- [ ] `create_docx` step (makes the file)
- [ ] A Word document shows up in the Created/artifacts panel, downloadable

**Known risk (be honest with yourself about this one):** this step doesn't
succeed every single time — it's noticeably better than it was, but not
bulletproof. **Rehearse this 2–3 times tonight and tomorrow morning before
the real thing.** If a run skips the knowledge-base step, or the AI just
types its findings in the chat instead of making the document, that run
"failed" — don't show that one live, just try again. If it works 2 times in
a row, you're in good shape for tomorrow.

---

## 3. Workflow B — Ask it to write and run code

**What you'll say to judges:** "It can also write and safely execute code,
fully sandboxed, no internet access."

**What to type:**
> Write a Python script that computes a pump's hydraulic power in
> kilowatts, using discharge pressure = 5.2 bar and flow rate = 250 cubic
> meters per hour, with P_kW = (pressure_bar * 1e5 * flow_m3h / 3600) / 1000.
> Print only the result rounded to 2 decimal places.

**What should happen:**
- [ ] `generate_code` step, then a separate `execute_code` step
- [ ] Output shown is `36.11`
- [ ] Fast and reliable — this workflow has been the most consistent one in
      testing, good one to do live without much rehearsal

---

## 4. Workflow D — The "how do you know it's offline" moment

This isn't a separate step — it's something to **point at the whole time**
you're doing 1–3 above.

- [ ] Bottom-left sovereignty/status indicator stays green throughout every
      step above, especially while Workflow B's code is actually running
      (that's the most convincing moment to point at it)
- [ ] If a judge asks "how do you actually know it's not calling out to the
      internet," you can say: there are six independent layers enforcing it,
      plus a log you can query afterward that proves zero outside
      connections happened during the whole session — not just "trust the
      UI"

---

## 5. If something looks broken

- Workflow A skips the knowledge-base step, or refuses to make the
  document → not a crash, just try the same prompt again in a **new**
  conversation (don't reuse the old one)
- Anything hangs for more than ~60 seconds → something's actually wrong,
  don't wait it out live, restart the backend
- Status indicator ever turns red → stop, don't continue the demo until you
  know why

---

## 6. About all the test data already in the app

We ran a lot of automated validation this week — dozens of test
conversations, documents, and generated files are sitting in the app right
now. That's expected from testing, not a bug, but it'll clutter the History
list and the Documents/Created pages if a judge starts clicking around.
Decide before tomorrow whether you want it cleaned up — see the note in
today's chat, or ask me to do it and I'll walk you through exactly what
gets removed and what stays.
