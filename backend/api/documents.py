"""Documents API endpoints.

POST /api/v1/documents - Upload a document for later reference by a Job.
GET /api/v1/documents - List previously uploaded documents.
GET /api/v1/documents/{document_id} - Get document metadata.

Per docs/api.md and docs/document-processing.md.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict

from backend.config import settings
from backend.repositories.documents import create_document, get_document, list_documents
from backend.utils.paths import uploads_path, UPLOADS_ROOT

router = APIRouter()
logger = logging.getLogger(__name__)

# MIME allowlist per docs/document-processing.md "Supported file types"
# JPEG/PNG + scanned PDFs (page images)
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}

# Max file size from config
MAX_FILE_SIZE_BYTES = settings.capabilities.extract_document.max_file_size_mb * 1024 * 1024


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str


class DocumentMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[DocumentMetadataResponse]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: dict


def _validate_upload(file: UploadFile) -> tuple[str, int]:
    """Validate uploaded file MIME type and size.

    Returns:
        (content_type, size_bytes)

    Raises:
        HTTPException: 400 if validation fails.
    """
    # Check MIME type - strict validation, no fallback to filename guessing
    content_type = file.content_type or ""
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_MIME_TYPE",
                    "message": f"File type '{content_type}' not allowed. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
                    "details": {"allowed_types": sorted(ALLOWED_MIME_TYPES)},
                }
            },
        )

    # Read file to check size
    file.file.seek(0, 2)  # Seek to end
    size_bytes = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": f"File size {size_bytes} bytes exceeds maximum {MAX_FILE_SIZE_BYTES} bytes ({settings.capabilities.extract_document.max_file_size_mb} MB)",
                    "details": {"max_size_bytes": MAX_FILE_SIZE_BYTES, "actual_size_bytes": size_bytes},
                }
            },
        )

    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "EMPTY_FILE",
                    "message": "Uploaded file is empty",
                    "details": {},
                }
            },
        )

    return content_type, size_bytes


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
    },
)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    """Upload a document for later reference by a Job.

    Accepts multipart/form-data with field 'file'.
    Validates MIME type against allowlist and size against configured limit.
    Stores file under data/uploads/{document_id}.{ext} and creates Document row.
    """
    # Validate
    content_type, size_bytes = _validate_upload(file)

    # Generate document_id and storage path
    from backend.utils.ids import new_id
    document_id = new_id()

    # Get extension from original filename
    original_filename = file.filename or "document"
    ext = Path(original_filename).suffix.lower()
    if not ext:
        # Guess from MIME type
        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "application/pdf": ".pdf",
        }
        ext = ext_map.get(content_type, ".bin")

    # Resolve scoped storage path
    try:
        storage_path = uploads_path(document_id, ext)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_FILENAME",
                    "message": str(e),
                    "details": {},
                }
            },
        )

    # Save file
    try:
        content = await file.read()
        with open(storage_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "STORAGE_ERROR",
                    "message": "Failed to save uploaded file",
                    "details": {},
                }
            },
        )

    # Create Document row with relative storage path
    relative_storage_path = storage_path.relative_to(UPLOADS_ROOT)
    returned_doc_id = create_document(
        filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=str(relative_storage_path),
        document_id=document_id,
    )

    # Get the created document for response
    doc = get_document(returned_doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "DOCUMENT_CREATION_FAILED",
                    "message": "Document record not found after creation",
                    "details": {},
                }
            },
        )

    logger.info(f"Document uploaded: {document_id} ({original_filename}, {size_bytes} bytes)")

    return DocumentUploadResponse(
        document_id=doc["document_id"],
        filename=doc["filename"],
        content_type=doc["content_type"],
        size_bytes=doc["size_bytes"],
        uploaded_at=doc["uploaded_at"],
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
)
async def list_documents_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    """List previously uploaded documents, most recently uploaded first.

    Mirrors GET /api/v1/knowledge-base's list shape (docs/api.md).
    """
    docs = list_documents(limit=limit, offset=offset)
    return DocumentListResponse(
        documents=[
            DocumentMetadataResponse(
                document_id=doc["document_id"],
                filename=doc["filename"],
                content_type=doc["content_type"],
                size_bytes=doc["size_bytes"],
                uploaded_at=doc["uploaded_at"],
            )
            for doc in docs
        ]
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentMetadataResponse,
    responses={
        404: {"model": ErrorResponse},
    },
)
async def get_document_metadata(document_id: str) -> DocumentMetadataResponse:
    """Get metadata for an uploaded document.

    Returns document metadata (not raw bytes).
    """
    # Validate UUID format
    try:
        UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"Document not found: {document_id}",
                    "details": {},
                }
            },
        )

    doc = get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"Document not found: {document_id}",
                    "details": {},
                }
            },
        )

    return DocumentMetadataResponse(
        document_id=doc["document_id"],
        filename=doc["filename"],
        content_type=doc["content_type"],
        size_bytes=doc["size_bytes"],
        uploaded_at=doc["uploaded_at"],
    )
