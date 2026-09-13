# Frontend (React + Vite + Tailwind)

## Hard rule

**The frontend never communicates with models, tools, or Docker directly.** Every interaction goes through the API layer defined in `api.md`. There is no code path in the frontend that calls Ollama, Chroma, or Docker's API — this is a security boundary (`security.md`), not a style preference.

## Page/layout structure

Originally a single-page app (`Workbench` only) for SIH; the Sidebar now
switches between three real pages via local state in `App.jsx` (no router
library added — `page`/`setPage` passed down through `AppShell`). `Jobs.jsx`,
`Knowledge.jsx`, `Audit.jsx`, `Settings.jsx` remain unwired mockups, not
listed below.

```
frontend/
├── src/
│   ├── App.jsx                    # owns `page` state, switches Workbench/Documents/Artifacts
│   ├── main.jsx
│   ├── pages/
│   │   ├── Workbench.jsx          # chat + live trace + artifacts + RAG evidence, for one Job
│   │   ├── Documents.jsx          # all uploaded documents (GET /api/v1/documents), cross-chat
│   │   └── Artifacts.jsx          # all generated artifacts (GET /api/v1/artifacts), cross-chat
│   ├── components/
│   │   ├── ChatPanel.jsx          # message history + input, file upload
│   │   ├── ConversationHistory.jsx # resume a past conversation (GET /api/v1/conversations)
│   │   ├── JobTracePanel.jsx      # live execution trace (SSE-driven)
│   │   ├── CapabilityActivity.jsx # renders one trace event (tool_invoked, tool_result, model_invoked, etc.)
│   │   ├── ArtifactPanel.jsx      # generated files for the current Job, download links
│   │   ├── RagEvidencePanel.jsx   # retrieval results for the current Job
│   │   ├── SovereigntyIndicator.jsx  # network-status badge (api.md#network-status), in StatusBar
│   │   ├── UploadButton.jsx
│   │   └── ErrorBanner.jsx
│   ├── hooks/
│   │   ├── useJobEvents.js        # SSE subscription for a job_id (owned by Workbench, shared down)
│   │   └── useApi.js              # thin fetch wrapper for api.md endpoints
│   └── services/
│       └── api.js                 # one function per api.md endpoint — no fetch() calls elsewhere
├── package.json
└── vite.config.js
```

## Chat

`ChatPanel` — message history for the current `conversation_id` (`GET /api/v1/conversations/{id}`), an input box, and a file-upload affordance. Submitting creates a Job (`POST /api/v1/jobs`) and immediately opens the trace panel for that `job_id`.

## Uploads

`UploadButton` calls `POST /api/v1/documents`, stores the returned `document_id`, attaches it to the next Job creation request. No client-side file processing — the file goes straight to the backend.

## Documents page

`Documents.jsx` — every uploaded document across all conversations (`GET /api/v1/documents`), since documents aren't scoped to a conversation in the data model. A simple table (filename, type, size, uploaded_at), polling every 10s. View-only — attaching a document to a message still happens via `UploadButton` in the Workbench composer.

## Created (Artifacts) page

`Artifacts.jsx` — every generated artifact across all Jobs (`GET /api/v1/artifacts`), each linking to `GET /api/v1/artifacts/{id}/download`. Same polling pattern as the Documents page.

## Conversation history

`ConversationHistory` — a dropdown (`GET /api/v1/conversations`) listing past conversations with a preview of the first message, most recently active first. Selecting one resumes it in the Workbench (drops to the empty-state composer with that conversation's full history loaded above it — no separate "history view" mode). "New chat" resets to a fresh, empty conversation.

## Job execution panel / live trace

`JobTracePanel`, driven by `useJobEvents(job_id)` subscribing to `GET /api/v1/jobs/{job_id}/events` (SSE). Renders each event as it arrives via `CapabilityActivity`, keyed by `event_type` (`audit.md`'s event-type table) — e.g., `tool_invoked` shows "Calling extract_document...", `resource_loaded` shows "Loading qwen3.5:9b...", `policy_decision` shows an allow/deny badge. On mount, first fetches `GET /api/v1/jobs/{job_id}/trace` (for late-join/refresh cases) then switches to the live SSE stream.

## Capability/tool activity

Rendered inline in the trace, not a separate panel — the trace *is* the capability/model activity view, per the "Job trace = filtered Audit stream" principle (`audit.md`).

## Model/resource activity

Same mechanism — `resource_loaded`/`resource_unloaded`/`model_invoked` events render as trace entries, giving the visible "watch it swap models" moment referenced in `demo.md`.

## Artifacts

`ArtifactPanel` lists artifacts for the current Job (from the Job's `artifact_ids`, `GET /api/v1/jobs/{job_id}`), each linking to `GET /api/v1/artifacts/{artifact_id}/download`.

## Downloads

Direct links to the download endpoint — browser-native download handling, no client-side blob manipulation needed.

## RAG evidence

`RagEvidencePanel` — when a Job's trace includes a `search_knowledge_base` `tool_invoked`/`tool_result` pair, render the returned `results[]` (title, chunk snippet, score) so retrieval grounding is visible, not just asserted in the chat response.

## Sovereignty indicator

`SovereigntyIndicator` polls `GET /api/v1/network-status` (`api.md`) on an interval (e.g., every 2s) and renders a persistent "0 external connections" state — independent of any specific Job, always visible during the demo.

## Errors

`ErrorBanner` — surfaces `error` events from the trace stream and any HTTP-level errors from `api.js` calls, using the error shape from `api.md`.

## Loading states

Standard per-component loading states (Job creation in flight, trace connecting, artifact rendering in progress) — driven by request/SSE-connection state, nothing exotic needed at this scope.

## API integration

`services/api.js` — one function per `api.md` endpoint, all fetch calls centralized here. No component calls `fetch()` directly.

## SSE handling

`hooks/useJobEvents.js` wraps `EventSource`, parses each `data:` line as one event object (`audit.md`'s schema), exposes an array of received events plus connection status to the consuming component.

## State management

React state + the two hooks above is sufficient at this scope — no additional state-management library needed. `Workbench.jsx` holds `conversation_id` and the active `job_id`; everything else derives from API calls/SSE scoped to those IDs.

## Component structure

Kept flat and purpose-specific, as listed above — no premature abstraction into a generic component library for a single-page SIH demo UI.
