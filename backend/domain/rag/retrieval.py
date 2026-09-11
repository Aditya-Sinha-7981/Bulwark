"""RAG retrieval pipeline (Task 12.b).

Implements `docs/rag.md` "Retrieval" exactly: embed the query -> vector
similarity search against the Chroma `knowledge_base` collection -> apply the
locked 0.50 relevance floor -> shape hits as
`{kb_document_id, title, chunk_text, score}`. No reranking (`docs/rag.md`
"Reranking" — not for SIH).

Invoked only by `domain/capabilities/search_knowledge_base.py`'s executor,
itself only invoked by the Job Manager after an explicit Orchestrator
`search_knowledge_base` proposal validated by Policy (ADR-03, `AGENTS.md`
§6 rule 5). This module never runs on its own initiative and never prepends
retrieved context anywhere — there is no other caller.

Reuses Task 12.a's Chroma client/collection accessor (`ingestion.get_kb_collection`)
rather than opening a second `PersistentClient` against the same on-disk path
(`tasks/12a-rag-ingestion.md` §10 "Known Risks", coordinated per
`tasks/12b-rag-retrieval.md` §4 "May Modify If Required").
"""

from __future__ import annotations

from typing import Any

from backend.domain.model_runtime.runtime import (
    ModelRuntimeError,
    ModelRuntimeUnavailableError,
    runtime as model_runtime,
)
from backend.domain.rag.ingestion import get_kb_collection

# Locked relevance floor (tasks/12b-rag-retrieval.md §7 Requirement 1, §11
# "Resolved (finalisation decision)"). A named, in-code constant — change
# only via documented retrieval-quality testing (Task 19), never ad hoc.
RELEVANCE_FLOOR = 0.50

# Hard upper bound on top_k actually sent to Chroma, regardless of what the
# (schema-validated, but otherwise unbounded) caller-supplied value is
# (§7 Error Handling: "do not pass an unbounded value to Chroma").
MAX_TOP_K = 50


class RetrievalError(Exception):
    """Retrieval could not be completed — distinct from a genuine empty
    result (`docs/rag.md` "Retrieval failure"). Raised for: an embedding-model
    failure, a Chroma query error, or an empty/uninitialised `knowledge_base`
    collection (nothing has ever been ingested). Callers must not catch this
    and silently return `results: []` — it is the `status: failed` signal;
    below-floor hits from a populated collection are `results: []` returned
    normally, not this exception.
    """


def _distance_to_similarity(distance: float) -> float:
    """Convert a Chroma distance to a higher-is-better similarity in (0, 1].

    Chroma's default collection space is squared L2 (unbounded, lower =
    closer) — Task 12.a created the `knowledge_base` collection with
    `get_or_create_collection(name=...)` and no explicit metric, so this is
    what retrieval must convert (`tasks/12b-rag-retrieval.md` §10 "Known
    Risks": "Chroma may return a distance rather than a similarity...
    convert... and document the conversion").

    Uses `1 / (1 + distance)`: bounded to (0, 1], monotonically decreasing in
    distance, and does not assume the embedding vectors are unit-normalized
    (unlike the `1 - distance/2` cosine-from-L2 shortcut, which only holds for
    unit vectors and would otherwise need clamping). This is a documented
    approximation, not a calibrated probability — the 0.50 floor may need
    retuning against `qwen3-embedding:0.6b`'s actual score distribution during
    Task 19's retrieval-quality testing, per the locked floor-tuning process.
    """
    return 1.0 / (1.0 + distance)


async def retrieve(
    query: str,
    top_k: int = 5,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run the retrieval pipeline for one query.

    Returns a list of `{kb_document_id, title, chunk_text, score}` dicts,
    already floor-filtered (only `score >= RELEVANCE_FLOOR`) and ordered by
    score descending. An empty list is a legitimate, successful result — a
    populated collection with no hit at or above the floor is genuinely "no
    grounding", not a failure (`docs/rag.md` "Retrieval failure").

    Raises:
        RetrievalError: query embedding failed, the Chroma query itself
            failed, or the `knowledge_base` collection is empty/uninitialised.
    """
    bounded_top_k = max(1, min(top_k, MAX_TOP_K))

    try:
        collection = get_kb_collection()
        chunk_count = collection.count()
    except Exception as exc:
        raise RetrievalError(f"Could not access Chroma knowledge_base collection: {exc}") from exc

    if chunk_count == 0:
        raise RetrievalError(
            "knowledge_base collection is empty or uninitialised — nothing has been ingested yet"
        )

    try:
        embed_result = await model_runtime.embed("embedding", query, job_id=job_id)
    except (ModelRuntimeUnavailableError, ModelRuntimeError) as exc:
        raise RetrievalError(f"Query embedding failed: {exc}") from exc

    if not embed_result.embeddings:
        raise RetrievalError("Query embedding returned no vector")
    query_vector = embed_result.embeddings[0]

    try:
        raw = collection.query(query_embeddings=[query_vector], n_results=bounded_top_k)
    except Exception as exc:
        raise RetrievalError(f"Chroma query failed: {exc}") from exc

    metadatas = (raw.get("metadatas") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for metadata, chunk_text, distance in zip(metadatas, documents, distances):
        score = _distance_to_similarity(distance)
        if score < RELEVANCE_FLOOR:
            continue
        hits.append(
            {
                "kb_document_id": metadata.get("kb_document_id"),
                "title": metadata.get("title"),
                "chunk_text": chunk_text,
                "score": score,
            }
        )

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits
