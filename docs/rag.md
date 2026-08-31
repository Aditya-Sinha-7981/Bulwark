# RAG (Retrieval-Augmented Generation)

## Principle

A pipeline, invoked only when the Orchestrator explicitly proposes `search_knowledge_base` (ADR-03, `decisions.md`) — never automatically run on every turn.

## Ingestion pipeline

`POST /api/v1/knowledge-base/documents` (see `api.md`) triggers, as a background task:

1. **Parsing** — extract raw text from the uploaded document (plain text/markdown for SIH seed documents; PDF text-layer extraction if a text-bearing PDF is ingested — the OCR pipeline in `document-processing.md` is for *query-time* extraction of scanned inputs, not knowledge-base ingestion, which is expected to be clean source material).
2. **Chunking** — fixed-size chunks (~500 tokens) with ~50-token overlap. Simple, predictable, sufficient at demo corpus scale — no semantic chunking needed for SIH.
3. **Metadata** — each chunk tagged with `kb_document_id`, `title`, `category` (if provided), `chunk_index`.
4. **Embedding** — via the `embedding` resource type (Model Runtime → `qwen3-embedding:0.6b`).
5. **Indexing** — chunk vector + metadata written to Chroma, collection name `knowledge_base`.
6. `KnowledgeBaseDocument.status` moves `ingesting` → `ready` (or `failed`, with the reason recorded).

## Retrieval

Triggered by the Orchestrator's `search_knowledge_base` proposal (`capabilities.md`):

1. Embed the query string (`embedding` resource type).
2. Vector similarity search against the `knowledge_base` Chroma collection, `top_k` (default 5, per the capability's input schema).
3. Return `chunk_text`, `title`, `score` per result — no reranking for SIH (see below).

## Reranking

**Not implemented for SIH.** Plain vector similarity is expected to be sufficient at demo-corpus scale. Add only if retrieval quality genuinely disappoints during testing (`testing.md`) — do not build it preemptively.

## Context construction for the Orchestrator

Retrieval results are returned to the Orchestrator in the standard tool-result shape (`agent.md`) — an array of `{ kb_document_id, title, chunk_text, score }`. The Orchestrator is responsible for deciding whether the results are sufficient to ground an answer; if `results` is empty or clearly irrelevant, the correct behavior is an honest "I don't have grounding for that" response, not fabrication from general model knowledge (this is explicitly tested — see Workflow C, test case C2, in `testing.md`).

## Evidence/citations

When the Orchestrator's final answer uses retrieved content, its `respond` content should reference which `kb_document_id`/`title` it drew from (a prompt-level instruction, not a separate mechanism) — the frontend's RAG-evidence panel (`frontend.md`) displays the retrieval results from that Job's trace regardless, so this is a readability nicety for the chat response, not the sole source of evidence.

## Document updates and deletion

- **Update:** re-ingest as a new `KnowledgeBaseDocument` (delete + re-add) — no in-place chunk update for SIH scope.
- **Deletion:** `DELETE /api/v1/knowledge-base/documents/{kb_document_id}` removes the SQLite row and all associated chunks from the Chroma collection (filtered by `kb_document_id` metadata).

## Duplicate handling

No automatic duplicate detection for SIH — re-ingesting the same source document creates a second `KnowledgeBaseDocument` with its own chunks. Not a concern at demo corpus scale; flagged here so it's a known, accepted gap rather than a silent one.

## Retrieval failure

An empty Chroma collection, an embedding-model load failure, or a Chroma query error are all returned to the Orchestrator as a failed `CapabilityExecution` result (`status: failed`) — never silently returned as an empty-but-successful result, since the Orchestrator needs to distinguish "genuinely no relevant documents" from "retrieval itself broke."

## Knowledge-base boundaries

The knowledge base for SIH is seeded with **synthetic** SOP-style documents the team authors — never real organizational data (none is available, and using anything else would misrepresent the demo). This is a demo-content decision, not an architectural one, but worth stating here so it isn't lost: whoever seeds the knowledge base should write realistic-looking maintenance/procedure documents, not placeholder lorem-ipsum text, since Workflow C's grounded-answer quality depends on this content being genuinely searchable.

## Explicit invocation — restated

To be unambiguous, since this is a locked architectural principle (ADR-03): there is no code path anywhere in the system that runs retrieval without an explicit `search_knowledge_base` proposal from the Orchestrator, validated by Policy like any other capability call. If you find yourself writing code that "helpfully" prepends retrieved context to every Orchestrator turn, stop — that violates this document and `decisions.md`.
