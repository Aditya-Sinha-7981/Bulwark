"""Knowledge-base API endpoints.

POST /api/v1/knowledge-base/documents - Ingest a document (background task).
GET /api/v1/knowledge-base - List ingested documents.
DELETE /api/v1/knowledge-base/documents/{kb_document_id} - Remove a document.

Per docs/api.md and docs/rag.md. Ingestion itself lives in
`domain/rag/ingestion.py` — this router only validates the request, persists
the initial row + source file, and schedules the background task.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.domain.rag.ingestion import delete_document_chunks, ingest_document
from backend.repositories.knowledge_base import (
    create_kb_document,
    delete_kb_document,
    get_kb_document,
    list_kb_documents,
)
from backend.utils.paths import uploads_path, UPLOADS_ROOT

router = APIRouter()
logger = logging.getLogger(__name__)

# Source documents ingestion accepts. PDF is text-layer extraction only
# (docs/rag.md); scanned-input OCR is a query-time concern, not ingestion.
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


class IngestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    category: Optional[str] = None


class IngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kb_document_id: str
    status: str


class KbDocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kb_document_id: str
    title: str
    status: str
    chunk_count: int


class KbDocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[KbDocumentSummary]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: dict


def _error(status_code: int, code: str, message: str, details: Optional[dict] = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": details or {}}},
    )


@router.post(
    "/knowledge-base/documents",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}},
)
async def ingest_kb_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(default=None),
) -> IngestResponse:
    """Accept a source document, persist it, and schedule background ingestion.

    Returns 202 immediately with status "ingesting" — parsing, chunking,
    embedding, and indexing happen asynchronously (docs/backend.md
    "Background jobs": FastAPI BackgroundTasks, no external queue).
    """
    parsed_metadata = IngestMetadata()
    if metadata:
        try:
            parsed_metadata = IngestMetadata(**json.loads(metadata))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_METADATA",
                f"metadata must be a JSON object with optional 'title'/'category': {exc}",
            )

    content_type = file.content_type or ""
    original_filename = file.filename or "document"
    ext = Path(original_filename).suffix.lower()

    if content_type not in ALLOWED_CONTENT_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_MIME_TYPE",
            f"File type '{content_type}' (extension '{ext}') not allowed for KB ingestion. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            {"allowed_extensions": sorted(ALLOWED_EXTENSIONS)},
        )

    content = await file.read()
    if not content:
        raise _error(status.HTTP_400_BAD_REQUEST, "EMPTY_FILE", "Uploaded file is empty")

    title = parsed_metadata.title or Path(original_filename).stem

    from backend.utils.ids import new_id

    kb_document_id = new_id()
    if not ext:
        ext = ".txt" if content_type != "application/pdf" else ".pdf"

    try:
        storage_path = uploads_path(kb_document_id, ext)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
    except ValueError as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_FILENAME", str(exc))

    try:
        with open(storage_path, "wb") as f:
            f.write(content)
    except OSError as exc:
        logger.error("Failed to save KB source file: %s", exc)
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "STORAGE_ERROR", "Failed to save uploaded file")

    relative_storage_path = str(storage_path.relative_to(UPLOADS_ROOT))

    created_id = create_kb_document(
        title=title,
        storage_path=relative_storage_path,
        category=parsed_metadata.category,
        status="ingesting",
    )

    background_tasks.add_task(
        ingest_document,
        kb_document_id=created_id,
        storage_path=str(storage_path),
        title=title,
        category=parsed_metadata.category,
        content_type=content_type,
    )

    logger.info("KB ingestion scheduled: kb_document_id=%s title=%s", created_id, title)

    return IngestResponse(kb_document_id=created_id, status="ingesting")


@router.get(
    "/knowledge-base",
    response_model=KbDocumentListResponse,
)
async def list_kb_documents_endpoint() -> KbDocumentListResponse:
    """List ingested knowledge-base documents (docs/api.md documented shape)."""
    docs = list_kb_documents()
    return KbDocumentListResponse(
        documents=[
            KbDocumentSummary(
                kb_document_id=doc["kb_document_id"],
                title=doc["title"],
                status=doc["status"],
                chunk_count=doc["chunk_count"],
            )
            for doc in docs
        ]
    )


@router.delete(
    "/knowledge-base/documents/{kb_document_id}",
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}},
)
async def delete_kb_document_endpoint(kb_document_id: str) -> dict:
    """Remove a KB document's SQLite row and all its Chroma chunks."""
    doc = get_kb_document(kb_document_id)
    if not doc:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "KB_DOCUMENT_NOT_FOUND",
            f"Knowledge-base document not found: {kb_document_id}",
        )

    delete_document_chunks(kb_document_id)
    delete_kb_document(kb_document_id)

    logger.info("KB document deleted: kb_document_id=%s", kb_document_id)

    return {"kb_document_id": kb_document_id, "deleted": True}
