"""extract_document capability executor.

validate_input → scoped upload path → pipeline → validate_output
(docs/capabilities.md#extract_document). Called only after Policy (Task 15).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from backend.config import settings
from backend.domain.capabilities.registry import (
    CapabilityRegistry,
    CapabilityValidationError,
)
from backend.domain.document_processing.pipeline import (
    OCRTimeoutError,
    PipelineTimeoutError,
    UnreadableDocumentError,
    process_document,
    process_pdf_document,
)
from backend.models.schemas import ExtractDocumentInput, ExtractDocumentOutput
from backend.repositories.documents import get_document
from backend.utils.paths import UPLOADS_ROOT

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}

MAX_FILE_SIZE_BYTES = settings.capabilities.extract_document.max_file_size_mb * 1024 * 1024


class ExtractDocumentError(Exception):
    """Raised when extract_document capability fails."""

    def __init__(self, message: str, status: str = "failed"):
        self.message = message
        self.status = status
        super().__init__(message)


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(settings.capabilities)


def _scoped_upload_path(storage_path: str) -> Path:
    relative = Path(storage_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ExtractDocumentError(f"Invalid document storage path: {storage_path}")
    file_path = (UPLOADS_ROOT / relative).resolve()
    try:
        file_path.relative_to(UPLOADS_ROOT.resolve())
    except ValueError as exc:
        raise ExtractDocumentError(f"Document path escapes uploads root: {storage_path}") from exc
    return file_path


async def execute_extract_document(
    input_data: Union[ExtractDocumentInput, dict],
    job_id: Union[str, None] = None,
) -> ExtractDocumentOutput:
    registry = _registry()
    payload = (
        {"document_id": str(input_data.document_id)}
        if isinstance(input_data, ExtractDocumentInput)
        else input_data
    )
    try:
        validated_input = registry.validate_input("extract_document", payload)
    except CapabilityValidationError as exc:
        raise ExtractDocumentError(f"Invalid extract_document input: {exc}") from exc

    document_id = str(validated_input.document_id)
    logger.info("Executing extract_document for document %s", document_id)

    doc = get_document(document_id)
    if not doc:
        raise ExtractDocumentError(f"Document not found: {document_id}")

    try:
        file_path = _scoped_upload_path(doc["storage_path"])
    except ExtractDocumentError:
        raise

    if not file_path.exists():
        raise ExtractDocumentError(f"Document file not found on disk: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ExtractDocumentError(
            f"File size {file_size} bytes exceeds maximum {MAX_FILE_SIZE_BYTES} bytes"
        )

    content_type = doc["content_type"]
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in ALLOWED_MIME_TYPES:
        raise ExtractDocumentError(f"Unsupported file type for extraction: {content_type}")

    try:
        if content_type == "application/pdf":
            result = await process_pdf_document(document_id, str(file_path), job_id=job_id)
        else:
            result = await process_document(document_id, str(file_path), job_id=job_id)
    except (UnreadableDocumentError, OCRTimeoutError, PipelineTimeoutError) as exc:
        logger.error("Pipeline failed for document %s: %s", document_id, exc)
        raise ExtractDocumentError(str(exc)) from exc
    except ExtractDocumentError:
        raise
    except Exception as exc:
        logger.error("Pipeline failed for document %s: %s", document_id, exc)
        raise ExtractDocumentError(f"Extraction pipeline failed: {exc}") from exc

    try:
        validated_output = registry.validate_output(
            "extract_document",
            {
                "extracted_text": result.extracted_text,
                "extraction_method": result.extraction_method,
                "confidence": result.confidence,
                "warnings": result.warnings,
            },
        )
    except CapabilityValidationError as exc:
        raise ExtractDocumentError(f"Invalid extract_document output: {exc}") from exc

    logger.info(
        "extract_document completed for %s: method=%s confidence=%.2f",
        document_id,
        validated_output.extraction_method,
        validated_output.confidence,
    )
    return validated_output
