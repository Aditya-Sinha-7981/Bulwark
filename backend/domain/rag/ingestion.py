"""Knowledge-base ingestion pipeline.

Implements `docs/rag.md` "Ingestion pipeline" exactly: parse -> chunk -> tag
metadata -> embed -> index into Chroma, with `KnowledgeBaseDocument` lifecycle
tracking. Invoked only as a background task from `api/knowledge_base.py` — this
module is never part of the Orchestrator loop and never triggers retrieval
(ADR-03, `AGENTS.md` §6 rule 5).

Frozen contract shared with Task 12.b (retrieval):
- Chroma collection name: "knowledge_base"
- Chunk metadata fields: kb_document_id, title, category, chunk_index
- Chunk id format: "{kb_document_id}:{chunk_index}"
"""

from __future__ import annotations

import logging
from typing import Optional

import chromadb

from backend.domain.audit.events import emit
from backend.domain.model_runtime.runtime import (
    ModelRuntimeError,
    ModelRuntimeUnavailableError,
    runtime as model_runtime,
)
from backend.repositories.knowledge_base import update_kb_document
from backend.utils.paths import chroma_dir

logger = logging.getLogger(__name__)


# Frozen Chroma collection name — the entire shared surface with Task 12.b
# (retrieval). Do not rename without coordinating (`tasks/12a-rag-ingestion.md`
# §10 "Known Risks").
KB_COLLECTION_NAME = "knowledge_base"

# Chunking heuristic (locked, docs/rag.md + task §7 Requirement 3):
# character-based approximation of "~500 tokens / ~50 overlap" at ~4 chars/token.
# Deterministic — same input always produces the same chunk boundaries.
CHUNK_SIZE_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200


class IngestionError(Exception):
    """Raised for any failure during parse/chunk/embed/index — caught by the
    background-task entrypoint and turned into status: failed + an audit event.
    """


# ---------------------------------------------------------------------------
# Chroma client — one persistent client per process, reused across calls.
# Avoids opening many clients against the same on-disk path (§10 "Known Risks").
# ---------------------------------------------------------------------------

_chroma_client: Optional["chromadb.ClientAPI"] = None


def get_chroma_client() -> "chromadb.ClientAPI":
    """Return the process-wide persistent Chroma client, creating it lazily."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(chroma_dir()))
    return _chroma_client


def reset_chroma_client() -> None:
    """Drop the cached client so the next call re-reads `chroma_dir()`.

    Used by tests that point `chroma_dir()` at a temporary directory per test.
    """
    global _chroma_client
    _chroma_client = None


def get_kb_collection() -> "chromadb.Collection":
    """Return the frozen `knowledge_base` Chroma collection, creating it if absent."""
    client = get_chroma_client()
    return client.get_or_create_collection(name=KB_COLLECTION_NAME)


# ---------------------------------------------------------------------------
# Requirement 1 step 1 — Parsing
# ---------------------------------------------------------------------------


def parse_document(storage_path: str, content_type: Optional[str] = None) -> str:
    """Extract raw text from a source file.

    Supports plain text/markdown directly, and the text layer of a text-bearing
    PDF. No OCR — scanned-input extraction is a query-time concern
    (`docs/document-processing.md`), not knowledge-base ingestion.

    Raises:
        IngestionError: If the file cannot be parsed or contains no text.
    """
    lower_path = storage_path.lower()
    is_pdf = lower_path.endswith(".pdf") or content_type == "application/pdf"

    if is_pdf:
        text = _parse_pdf_text(storage_path)
    else:
        text = _parse_plain_text(storage_path)

    if not text or not text.strip():
        raise IngestionError(f"No extractable text in source file: {storage_path}")

    return text


def _parse_plain_text(storage_path: str) -> str:
    try:
        with open(storage_path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise IngestionError(f"Could not read source file: {exc}") from exc

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"Source file is not valid UTF-8 text: {exc}") from exc


def _parse_pdf_text(storage_path: str) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise IngestionError("pypdfium2 is required to extract PDF text") from exc

    try:
        pdf = pdfium.PdfDocument(storage_path)
    except Exception as exc:
        raise IngestionError(f"Could not open PDF: {exc}") from exc

    try:
        page_texts: list[str] = []
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            try:
                textpage = page.get_textpage()
                try:
                    page_texts.append(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
        return "\n\n".join(page_texts)
    except Exception as exc:
        raise IngestionError(f"Could not extract PDF text: {exc}") from exc
    finally:
        pdf.close()


# ---------------------------------------------------------------------------
# Requirement 1 step 2 / Requirement 3 — Chunking (locked heuristic)
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Split text into deterministic fixed-size chunks with overlap.

    Character-based (not model tokens) per the locked decision in
    `tasks/12a-rag-ingestion.md` §7 Requirement 3 — a ~4-chars-per-token
    approximation of `docs/rag.md`'s "~500 tokens / ~50 overlap". Same input
    always produces the same chunk boundaries (deterministic; no semantic
    chunking, no tokenizer dependency).
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    stripped = text.strip()
    if not stripped:
        return []

    chunks: list[str] = []
    step = chunk_size - overlap
    start = 0
    length = len(stripped)

    while start < length:
        end = min(start + chunk_size, length)
        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += step

    return chunks


# ---------------------------------------------------------------------------
# Requirement 1 steps 3-5 — Metadata, embedding, indexing
# ---------------------------------------------------------------------------


async def ingest_document(
    kb_document_id: str,
    storage_path: str,
    title: str,
    category: Optional[str] = None,
    content_type: Optional[str] = None,
) -> None:
    """Run the full ingestion pipeline for one already-persisted KB document row.

    On success: `KnowledgeBaseDocument.status` -> "ready" with `chunk_count`
    and `ingested_at` set.
    On any failure: status -> "failed", any partially-written Chroma chunks
    for this `kb_document_id` are cleaned up, and the reason is recorded via
    the `error` audit event (`job_id=None`) — no new DB field
    (`tasks/12a-rag-ingestion.md` §6 "Audit / Events", locked decision).
    """
    collection = get_kb_collection()

    try:
        text = parse_document(storage_path, content_type=content_type)
        chunks = chunk_text(text)
        if not chunks:
            raise IngestionError("Document produced zero chunks after parsing")

        embeddings = await _embed_chunks(chunks)

        ids = [f"{kb_document_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "kb_document_id": kb_document_id,
                "title": title,
                "category": category or "",
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        try:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=chunks,
            )
        except Exception as exc:
            raise IngestionError(f"Chroma write failed: {exc}") from exc

        from datetime import datetime, timezone

        update_kb_document(
            kb_document_id=kb_document_id,
            status="ready",
            chunk_count=len(chunks),
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "KB ingestion complete: kb_document_id=%s chunks=%d", kb_document_id, len(chunks)
        )

    except (IngestionError, ModelRuntimeUnavailableError, ModelRuntimeError) as exc:
        await _fail_ingestion(collection, kb_document_id, str(exc))
    except Exception as exc:  # noqa: BLE001 — any unexpected failure must still fail cleanly
        logger.exception("Unexpected KB ingestion failure for %s", kb_document_id)
        await _fail_ingestion(collection, kb_document_id, f"Unexpected error: {exc}")


async def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    result = await model_runtime.embed("embedding", chunks)
    return result.embeddings


async def _fail_ingestion(collection: "chromadb.Collection", kb_document_id: str, reason: str) -> None:
    """Clean up any partially-written chunks, mark the document failed, and
    record the reason via the `error` audit event (job-independent)."""
    try:
        collection.delete(where={"kb_document_id": kb_document_id})
    except Exception:
        logger.exception("Failed to clean up partial Chroma chunks for %s", kb_document_id)

    update_kb_document(kb_document_id=kb_document_id, status="failed")

    await emit(
        "error",
        "rag_ingestion",
        {
            "component": "rag_ingestion",
            "message": reason,
            "context": {"kb_document_id": kb_document_id},
        },
        job_id=None,
    )
    logger.warning("KB ingestion failed: kb_document_id=%s reason=%s", kb_document_id, reason)


def delete_document_chunks(kb_document_id: str) -> None:
    """Remove all Chroma chunks for a `kb_document_id` (used by DELETE)."""
    collection = get_kb_collection()
    collection.delete(where={"kb_document_id": kb_document_id})
