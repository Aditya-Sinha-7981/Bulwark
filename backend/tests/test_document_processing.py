"""Tests for OCR / document processing (Task 11).

Per docs/testing.md "OCR tests": confirm escalation triggers correctly per signal,
not just on one confidence number.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
for _path in (str(_REPO_ROOT), str(_BACKEND_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# With pytest.ini pythonpath = ., modules are importable directly
from main import app
from domain.document_processing.pipeline import (
    ARTIFACT_KEYS,
    ExtractionResult,
    OCRTimeoutError,
    QualitySignals,
    SIGNAL_KEYS,
    UnreadableDocumentError,
    assess_quality,
    process_document,
    process_multi_page_document,
    process_pdf_document,
    should_escalate,
)
from domain.document_processing.ocr import (
    OCR_PASS_TIMEOUT_SECONDS,
    OCRResult,
    OCRRegion,
    OCREngine,
    _normalize_bbox,
    _region_type_from_layout,
    extract_pdf_pages,
    run_ocr,
)
from domain.capabilities.extract_document import execute_extract_document, ExtractDocumentError
from backend.models.schemas import ExtractDocumentInput, ExtractDocumentOutput
from backend.domain.capabilities.registry import CapabilityRegistry
# `backend.repositories.documents`, not the bare `repositories.documents` —
# the bare import resolves to a *separate* sys.modules entry (both `backend/`
# and the repo root are on sys.path here), so patching the bare module's
# get_connection (which nothing did) left every create_document/get_document
# call in this file hitting the real data/db/app.db. Confirmed live: 718 of
# 721 rows in the real `documents` table were test fixtures from this file
# (cleaned up 2026-09-13 — logs/feature-integration.md).
from backend.repositories.documents import create_document, get_document
from config import settings


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_db(isolated_db):
    """Isolated temp SQLite DB (conftest.py `isolated_db`), patched into
    every repository module including `backend.repositories.documents` —
    covers both the direct create_document()/get_document() calls in this
    file and, via the `client` fixture below, the HTTP-level ones."""
    return isolated_db


@pytest.fixture
def client(temp_db, tmp_path, monkeypatch):
    """TestClient bound to `temp_db` — must depend on it (not just isolated_db
    directly) so the patch is in place before any request is made.

    Also isolates uploaded-file *bytes*: `backend/api/documents.py` imports
    `uploads_path`/`UPLOADS_ROOT` by value at module load time
    (`from backend.utils.paths import ...`), so `isolated_db` alone doesn't
    touch it — every POST /documents in this file was writing real bytes
    into the real data/uploads/ even after the DB rows were fixed (caught
    live: 30 new orphaned files appeared after a single full-suite run).
    Patches this module's own bound names, same pattern as
    test_rag_ingestion.py's `env` fixture for the KB upload path.
    """
    import backend.api.documents as documents_api
    # This file imports extract_document via the bare `domain.capabilities.*`
    # path (line ~50), not `backend.domain.capabilities.*` — same dual-
    # sys.path trap as the create_document/get_document import fixed above,
    # so both module spellings need their own UPLOADS_ROOT patched.
    import backend.domain.capabilities.extract_document as extract_document_module
    import domain.capabilities.extract_document as extract_document_module_bare

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(documents_api, "UPLOADS_ROOT", uploads_dir)
    monkeypatch.setattr(documents_api, "uploads_path", lambda doc_id, ext: uploads_dir / f"{doc_id}{ext}")
    # extract_document.py has its own independent `from backend.utils.paths
    # import UPLOADS_ROOT` binding — reading an uploaded file back (not just
    # writing it) goes through this module, not backend.api.documents.
    monkeypatch.setattr(extract_document_module, "UPLOADS_ROOT", uploads_dir)
    monkeypatch.setattr(extract_document_module_bare, "UPLOADS_ROOT", uploads_dir)
    return TestClient(app)


@pytest.fixture
def sample_image():
    """Create a simple test image."""
    img = Image.new('RGB', (800, 600), color='white')
    # Add some text-like patterns
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Sample Document Text", fill='black')
    draw.text((50, 100), "Line 2: More content here", fill='black')
    draw.rectangle([50, 150, 750, 200], outline='black', width=2)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def uploaded_document(client, sample_image):
    """Upload a test document and return its ID."""
    files = {"file": ("test.png", sample_image, "image/png")}
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 201
    return response.json()["document_id"]





# ============================================================================
# Upload Endpoint Tests
# ============================================================================

class TestUploadEndpoint:
    """Tests for POST /api/v1/documents and GET /api/v1/documents/{id}."""

    def test_upload_allowed_image_png(self, client):
        """Upload a PNG image → 201."""
        img = Image.new('RGB', (100, 100), color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        files = {"file": ("test.png", buf.getvalue(), "image/png")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 201
        data = response.json()
        assert "document_id" in data
        assert data["filename"] == "test.png"
        assert data["content_type"] == "image/png"
        assert data["size_bytes"] > 0

    def test_upload_allowed_image_jpeg(self, client):
        """Upload a JPEG image → 201."""
        img = Image.new('RGB', (100, 100), color='white')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)

        files = {"file": ("test.jpg", buf.getvalue(), "image/jpeg")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 201

    def test_upload_allowed_pdf(self, client):
        """Upload a PDF → 201 (scanned PDF page images are allowed)."""
        # Create a minimal PDF
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {"file": ("test.pdf", pdf_content, "application/pdf")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 201

    def test_upload_disallowed_mime_type(self, client):
        """Upload a .txt file → 400 with error envelope."""
        files = {"file": ("test.txt", b"plain text", "text/plain")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"]["code"] == "INVALID_MIME_TYPE"

    def test_upload_oversize_file(self, client):
        """Upload a file exceeding max_file_size_mb → 400."""
        # Create a file larger than 10MB
        large_content = b"x" * (11 * 1024 * 1024)
        files = {"file": ("large.png", large_content, "image/png")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"]["code"] == "FILE_TOO_LARGE"

    def test_upload_empty_file(self, client):
        """Upload an empty file → 400."""
        files = {"file": ("empty.png", b"", "image/png")}
        response = client.post("/api/v1/documents", files=files)

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"]["code"] == "EMPTY_FILE"

    def test_get_document_metadata(self, client, uploaded_document):
        """GET /api/v1/documents/{id} returns metadata."""
        response = client.get(f"/api/v1/documents/{uploaded_document}")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == uploaded_document
        assert data["filename"] == "test.png"

    def test_get_nonexistent_document(self, client):
        """GET nonexistent document → 404."""
        response = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_list_documents_includes_uploaded(self, client, uploaded_document):
        """GET /api/v1/documents includes a just-uploaded document, most recent first."""
        response = client.get("/api/v1/documents")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        ids = [d["document_id"] for d in data["documents"]]
        assert uploaded_document in ids
        # Most recent upload should be at (or near) the front of a DESC-ordered list.
        assert ids[0] == uploaded_document

    def test_list_documents_respects_limit(self, client, uploaded_document):
        """GET /api/v1/documents?limit=1 returns at most one document."""
        response = client.get("/api/v1/documents", params={"limit": 1})

        assert response.status_code == 200
        assert len(response.json()["documents"]) == 1

    def test_list_documents_rejects_invalid_limit(self, client):
        """GET /api/v1/documents?limit=0 → 422 (validation)."""
        response = client.get("/api/v1/documents", params={"limit": 0})

        assert response.status_code == 422


# ============================================================================
# OCR Quality Assessment Tests
# ============================================================================

class TestQualityAssessment:
    """Tests for the multi-signal quality assessment (pipeline.py)."""

    def test_assess_quality_clean_ocr(self):
        """Clean OCR result → high confidence, no handwriting, good completeness."""
        regions = [
            OCRRegion(text="Hello world", confidence=0.95, bbox=[[0,0],[100,0],[100,20],[0,20]], region_type="text"),
            OCRRegion(text="This is a test", confidence=0.92, bbox=[[0,30],[120,30],[120,50],[0,50]], region_type="text"),
        ]
        ocr_result = OCRResult(
            full_text="Hello world\nThis is a test",
            regions=regions,
            mean_confidence=0.935,
            processing_time_ms=100,
            page_count=1,
            layout_analysis={
                "estimated_text_area": 0.15,
                "region_density": 2.0,
                "column_structure": [],
                "table_regions": 0,
            },
        )

        signals = assess_quality(ocr_result)

        assert signals.mean_ocr_confidence == 0.935
        assert signals.handwriting_detected is False
        assert signals.completeness_estimate > 0.8
        assert signals.layout_complexity_flag is False

    def test_assess_quality_low_confidence(self):
        """Low mean confidence → triggers mean_confidence_below."""
        regions = [
            OCRRegion(text="Unclear", confidence=0.5, bbox=[[0,0],[50,0],[50,20],[0,20]], region_type="text"),
            OCRRegion(text="Text", confidence=0.6, bbox=[[0,30],[40,30],[40,50],[0,50]], region_type="text"),
        ]
        ocr_result = OCRResult(
            full_text="Unclear\nText",
            regions=regions,
            mean_confidence=0.55,
            processing_time_ms=100,
            page_count=1,
            layout_analysis={
                "estimated_text_area": 0.15,
                "region_density": 2.0,
                "column_structure": [],
                "table_regions": 0,
            },
        )

        signals = assess_quality(ocr_result)

        assert signals.mean_ocr_confidence == 0.55
        assert signals.completeness_estimate > 0.8
        assert signals.handwriting_detected is False

    def test_assess_quality_handwriting_detected(self):
        """Handwriting regions detected → handwriting_detected = True."""
        regions = [
            OCRRegion(text="Handwritten note", confidence=0.4, bbox=[[0,0],[100,0],[100,20],[0,20]], region_type="handwriting"),
            OCRRegion(text="Printed text", confidence=0.9, bbox=[[0,30],[80,30],[80,50],[0,50]], region_type="text"),
        ]
        ocr_result = OCRResult(
            full_text="Handwritten note\nPrinted text",
            regions=regions,
            mean_confidence=0.65,
            processing_time_ms=100,
            page_count=1,
        )

        signals = assess_quality(ocr_result)

        assert signals.handwriting_detected is True

    def test_assess_quality_layout_complexity(self):
        """Table/vertical regions detected → layout_complexity_flag = True."""
        regions = [
            OCRRegion(text="Table cell", confidence=0.8, bbox=[[0,0],[50,0],[50,20],[0,20]], region_type="table"),
            OCRRegion(text="Table cell", confidence=0.8, bbox=[[50,0],[100,0],[100,20],[50,20]], region_type="table"),
        ]
        ocr_result = OCRResult(
            full_text="Table cell\nTable cell",
            regions=regions,
            mean_confidence=0.8,
            processing_time_ms=100,
            page_count=1,
        )

        signals = assess_quality(ocr_result)

        assert signals.layout_complexity_flag is True

    def test_assess_quality_empty_result(self):
        """Empty OCR result → all signals zero/false."""
        ocr_result = OCRResult(
            full_text="",
            regions=[],
            mean_confidence=0.0,
            processing_time_ms=100,
            page_count=1,
        )

        signals = assess_quality(ocr_result)

        assert signals.mean_ocr_confidence == 0.0
        assert signals.handwriting_detected is False
        assert signals.completeness_estimate == 0.0
        assert signals.layout_complexity_flag is False


# ============================================================================
# Escalation Decision Tests
# ============================================================================

class TestEscalationDecision:
    """Tests for should_escalate with configured thresholds."""

    def test_escalate_mean_confidence_below(self):
        """Mean confidence below 0.75 → escalate."""
        signals = QualitySignals(
            mean_ocr_confidence=0.70,
            handwriting_detected=False,
            completeness_estimate=0.9,
            layout_complexity_flag=False,
        )

        escalate, triggered = should_escalate(signals)

        assert escalate is True
        assert any("mean_confidence_below" in t for t in triggered)

    def test_escalate_completeness_below(self):
        """Completeness below 0.6 → escalate."""
        signals = QualitySignals(
            mean_ocr_confidence=0.8,
            handwriting_detected=False,
            completeness_estimate=0.5,
            layout_complexity_flag=False,
        )

        escalate, triggered = should_escalate(signals)

        assert escalate is True
        assert any("completeness_below" in t for t in triggered)

    def test_escalate_handwriting_detected(self):
        """Handwriting detected → escalate."""
        signals = QualitySignals(
            mean_ocr_confidence=0.9,
            handwriting_detected=True,
            completeness_estimate=0.9,
            layout_complexity_flag=False,
        )

        escalate, triggered = should_escalate(signals)

        assert escalate is True
        assert any("handwriting_detected" in t for t in triggered)

    def test_escalate_layout_complexity(self):
        """Layout complexity flag → escalate."""
        signals = QualitySignals(
            mean_ocr_confidence=0.9,
            handwriting_detected=False,
            completeness_estimate=0.9,
            layout_complexity_flag=True,
        )

        escalate, triggered = should_escalate(signals)

        assert escalate is True
        assert any("layout_complexity_flag" in t for t in triggered)

    def test_no_escalation_clean_document(self):
        """Clean document → no escalation."""
        signals = QualitySignals(
            mean_ocr_confidence=0.9,
            handwriting_detected=False,
            completeness_estimate=0.9,
            layout_complexity_flag=False,
        )

        escalate, triggered = should_escalate(signals)

        assert escalate is False
        assert len(triggered) == 0


# ============================================================================
# Pipeline Integration Tests (Mocked)
# ============================================================================

class TestPipelineIntegration:
    """Integration tests for the full pipeline with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_process_document_clean_ocr_no_escalation(self, temp_db):
        """Clean image → single OCR pass, extraction_method: ocr."""
        # Create a test document record
        doc_id = create_document(
            filename="clean.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="clean.png",
        )

        # Mock the OCR to return clean results
        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Clean document text\nExtracted successfully",
                regions=[
                    OCRRegion(text="Clean document text", confidence=0.95, bbox=[[0,0],[100,0],[100,20],[0,20]], region_type="text"),
                    OCRRegion(text="Extracted successfully", confidence=0.92, bbox=[[0,30],[120,30],[120,50],[0,50]], region_type="text"),
                ],
                mean_confidence=0.935,
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.15,
                    'region_density': 2.0,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            # Mock vision escalation (should not be called)
            with patch("domain.document_processing.pipeline.escalate_to_vision") as mock_vision:
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "ocr"
        assert "Clean document text" in result.extracted_text
        assert result.confidence > 0.9
        assert len(result.warnings) == 0
        mock_vision.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_document_low_confidence_triggers_escalation(self, temp_db):
        """Degraded image → escalation triggered by mean_confidence_below."""
        doc_id = create_document(
            filename="degraded.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="degraded.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Unclear text",
                regions=[
                    OCRRegion(text="Unclear", confidence=0.5, bbox=[[0,0],[50,0],[50,20],[0,20]], region_type="text"),
                ],
                mean_confidence=0.5,
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.05,
                    'region_density': 0.5,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = "Vision extracted: Clear text from vision model"
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "vision_escalation"
        assert "Vision extracted" in result.extracted_text
        assert result.confidence == 0.5
        assert any("mean_confidence_below" in w for w in result.warnings)
        assert any("remains low" in w for w in result.warnings)
        mock_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_document_handwriting_triggers_escalation(self, temp_db):
        """Handwritten image → escalation triggered by handwriting_detected."""
        doc_id = create_document(
            filename="handwritten.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="handwritten.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Partial text",
                regions=[
                    OCRRegion(text="Handwritten", confidence=0.85, bbox=[[0,0],[80,0],[80,20],[0,20]], region_type="handwriting", layout_score=0.9),
                    OCRRegion(text="Text", confidence=0.85, bbox=[[0,30],[40,30],[40,50],[0,50]], region_type="text"),
                ],
                mean_confidence=0.85,
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.12,
                    'region_density': 1.8,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = "Handwritten note transcribed by vision"
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "vision_escalation"
        assert any("handwriting_detected" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_process_document_handwriting_high_confidence_independent_escalation(self, temp_db):
        """Handwriting detected with HIGH confidence → escalation independent of confidence."""
        doc_id = create_document(
            filename="handwritten_high_conf.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="handwritten_high_conf.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Clear handwriting",
                regions=[
                    OCRRegion(text="Handwritten", confidence=0.92, bbox=[[0,0],[80,0],[80,20],[0,20]], region_type="handwriting", layout_score=0.95),
                    OCRRegion(text="Text", confidence=0.9, bbox=[[0,30],[40,30],[40,50],[0,50]], region_type="text"),
                ],
                mean_confidence=0.91,  # ABOVE 0.75 threshold
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.15,
                    'region_density': 2.0,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = "Clear handwriting transcribed"
                result = await process_document(doc_id, "fake_path.png")

        # Should escalate due to handwriting_detected even though confidence is high
        assert result.extraction_method == "vision_escalation"
        assert any("handwriting_detected" in w for w in result.warnings)
        assert result.signals.mean_ocr_confidence == 0.91

    @pytest.mark.asyncio
    async def test_process_document_completeness_only_triggers_escalation(self, temp_db):
        """Completeness below threshold → escalation with other signals good."""
        doc_id = create_document(
            filename="incomplete.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="incomplete.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Sparse",
                regions=[
                    OCRRegion(text="Sparse", confidence=0.85, bbox=[[0,0],[50,0],[50,20],[0,20]], region_type="text"),
                ],
                mean_confidence=0.85,  # Above threshold
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.01,  # Very low coverage
                    'region_density': 0.2,  # Very low density
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = "Completed text from vision"
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "vision_escalation"
        assert any("completeness_below" in w for w in result.warnings)
        assert result.signals.mean_ocr_confidence == 0.85  # Good confidence
        assert result.signals.handwriting_detected is False
        assert result.signals.layout_complexity_flag is False

    @pytest.mark.asyncio
    async def test_process_document_layout_complexity_only_triggers_escalation(self, temp_db):
        """Layout complexity flag → escalation with other signals good."""
        doc_id = create_document(
            filename="multicolumn.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="multicolumn.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Column 1 text\nColumn 2 text",
                regions=[
                    OCRRegion(text="Column 1 text", confidence=0.9, bbox=[[0,0],[100,0],[100,50],[0,50]], region_type="text"),
                    OCRRegion(text="Column 2 text", confidence=0.9, bbox=[[200,0],[300,0],[300,50],[200,50]], region_type="text"),
                ],
                mean_confidence=0.9,  # Above threshold
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.12,
                    'region_density': 1.5,
                    'column_structure': [
                        {'x_center': 50, 'region_count': 1},
                        {'x_center': 250, 'region_count': 1},
                    ],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = "Both columns extracted"
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "vision_escalation"
        assert any("layout_complexity_flag" in w for w in result.warnings)
        assert result.signals.mean_ocr_confidence == 0.9
        assert result.signals.handwriting_detected is False
        assert result.signals.completeness_estimate > 0.6

    @pytest.mark.asyncio
    async def test_process_document_corrupt_file(self, temp_db):
        """Corrupt/unreadable file → raises exception for executor to handle as failure."""
        doc_id = create_document(
            filename="corrupt.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="corrupt.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.side_effect = Exception("Cannot read file: corrupt")

            with pytest.raises(UnreadableDocumentError) as exc_info:
                await process_document(doc_id, "fake_path.png")

        assert "OCR failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_document_vision_unavailable_fallback(self, temp_db):
        """Vision unavailable during escalation → OCR-only result + warning."""
        doc_id = create_document(
            filename="needs_vision.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="needs_vision.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Poor OCR result",
                regions=[
                    OCRRegion(text="Poor", confidence=0.5, bbox=[[0,0],[40,0],[40,20],[0,20]], region_type="text"),
                ],
                mean_confidence=0.5,
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.03,
                    'region_density': 0.3,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                mock_vision.return_value = ""  # Vision unavailable returns empty
                result = await process_document(doc_id, "fake_path.png")

        assert result.extraction_method == "ocr"
        assert result.extracted_text == "Poor OCR result"
        assert any("vision" in w.lower() and "unavailable" in w.lower() for w in result.warnings)
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_process_multi_page_pdf_per_page_escalation(self, temp_db):
        """Multi-page PDF: page 1 OCR, page 2 vision, page 3 OCR."""
        doc_id = create_document(
            filename="mixed.pdf",
            content_type="application/pdf",
            size_bytes=3000,
            storage_path="mixed.pdf",
        )

        # Mock PDF page extraction
        with patch("domain.document_processing.pipeline.extract_pdf_pages") as mock_extract:
            mock_extract.return_value = ["page1.png", "page2.png", "page3.png"]
            
            # Mock OCR for each page
            ocr_results = [
                # Page 1: clean
                OCRResult(
                    full_text="Page 1 clean text",
                    regions=[OCRRegion(text="Page 1 clean text", confidence=0.95, bbox=[[0,0],[100,0],[100,20],[0,20]], region_type="text")],
                    mean_confidence=0.95,
                    processing_time_ms=50,
                    page_count=1,
                    layout_analysis={'estimated_text_area': 0.1, 'region_density': 1.0, 'column_structure': [], 'table_regions': 0},
                ),
                # Page 2: handwriting
                OCRResult(
                    full_text="Page 2 handwritten",
                    regions=[OCRRegion(text="Handwritten", confidence=0.4, bbox=[[0,0],[80,0],[80,20],[0,20]], region_type="handwriting")],
                    mean_confidence=0.4,
                    processing_time_ms=60,
                    page_count=1,
                    layout_analysis={'estimated_text_area': 0.08, 'region_density': 0.8, 'column_structure': [], 'table_regions': 0},
                ),
                # Page 3: clean
                OCRResult(
                    full_text="Page 3 clean text",
                    regions=[OCRRegion(text="Page 3 clean text", confidence=0.93, bbox=[[0,0],[100,0],[100,20],[0,20]], region_type="text")],
                    mean_confidence=0.93,
                    processing_time_ms=50,
                    page_count=1,
                    layout_analysis={'estimated_text_area': 0.1, 'region_density': 1.0, 'column_structure': [], 'table_regions': 0},
                ),
            ]
            
            with patch("domain.document_processing.pipeline.run_ocr", side_effect=ocr_results) as mock_ocr:
                with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock) as mock_vision:
                    mock_vision.return_value = "Page 2 handwritten transcribed by vision"
                    result = await process_pdf_document(doc_id, "fake.pdf")

        # Verify vision was called ONLY for page 2 (the one with handwriting)
        assert mock_vision.call_count == 1
        call_args = mock_vision.call_args_list[0]
        assert call_args[0][0] == "page2.png"  # Second page

        # Verify overall result
        assert result.extraction_method == "vision_escalation"
        assert "Page 1 clean text" in result.extracted_text
        assert "Page 2 handwritten transcribed by vision" in result.extracted_text
        assert "Page 3 clean text" in result.extracted_text

    @pytest.mark.asyncio
    async def test_process_pdf_page_ordering(self, temp_db):
        """Verify extracted text is assembled in original page order."""
        doc_id = create_document(
            filename="ordered.pdf",
            content_type="application/pdf",
            size_bytes=2000,
            storage_path="ordered.pdf",
        )

        with patch("domain.document_processing.pipeline.extract_pdf_pages") as mock_extract:
            mock_extract.return_value = ["page1.png", "page2.png", "page3.png"]
            
            ocr_results = [
                OCRResult(
                    full_text="First page content",
                    regions=[
                        OCRRegion(
                            text="First page content",
                            confidence=0.9,
                            bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
                            region_type="text",
                        )
                    ],
                    mean_confidence=0.9,
                    processing_time_ms=50,
                    page_count=1,
                    layout_analysis={
                        "estimated_text_area": 0.1,
                        "region_density": 1.0,
                        "column_structure": [],
                        "table_regions": 0,
                    },
                ),
                OCRResult(
                    full_text="Second page content",
                    regions=[
                        OCRRegion(
                            text="Second page content",
                            confidence=0.9,
                            bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
                            region_type="text",
                        )
                    ],
                    mean_confidence=0.9,
                    processing_time_ms=50,
                    page_count=1,
                    layout_analysis={
                        "estimated_text_area": 0.1,
                        "region_density": 1.0,
                        "column_structure": [],
                        "table_regions": 0,
                    },
                ),
                OCRResult(
                    full_text="Third page content",
                    regions=[
                        OCRRegion(
                            text="Third page content",
                            confidence=0.9,
                            bbox=[[0, 0], [100, 0], [100, 20], [0, 20]],
                            region_type="text",
                        )
                    ],
                    mean_confidence=0.9,
                    processing_time_ms=50,
                    page_count=1,
                    layout_analysis={
                        "estimated_text_area": 0.1,
                        "region_density": 1.0,
                        "column_structure": [],
                        "table_regions": 0,
                    },
                ),
            ]

            with patch("domain.document_processing.pipeline.run_ocr", side_effect=ocr_results):
                with patch(
                    "domain.document_processing.pipeline.escalate_to_vision",
                    new_callable=AsyncMock,
                ) as mock_vision:
                    result = await process_pdf_document(doc_id, "fake.pdf")
                    mock_vision.assert_not_called()

        # Verify page order in assembled text
        text = result.extracted_text
        first_idx = text.index("First page content")
        second_idx = text.index("Second page content")
        third_idx = text.index("Third page content")
        
        assert first_idx < second_idx < third_idx


# ============================================================================
# Capability Executor Tests
# ============================================================================

class TestExtractDocumentExecutor:
    """Tests for the extract_document capability executor."""

    @pytest.mark.asyncio
    async def test_execute_extract_document_success(self, temp_db, uploaded_document):
        """Valid document → returns validated ExtractDocumentOutput."""
        with patch("domain.capabilities.extract_document.process_document", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = ExtractionResult(
                extracted_text="Extracted text from document",
                extraction_method="ocr",
                confidence=0.92,
                warnings=[],
                signals=QualitySignals(0.92, False, 0.95, False),
                processing_time_ms=500,
            )

            input_data = ExtractDocumentInput(document_id=uploaded_document)
            result = await execute_extract_document(input_data)

        assert isinstance(result, ExtractDocumentOutput)
        assert result.extracted_text == "Extracted text from document"
        assert result.extraction_method == "ocr"
        assert result.confidence == 0.92
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_execute_extract_document_success_pdf(self, temp_db, client):
        """Valid PDF document → processes pages and returns validated output."""
        # Upload a real PDF first
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {"file": ("test.pdf", pdf_content, "application/pdf")}
        response = client.post("/api/v1/documents", files=files)
        assert response.status_code == 201
        doc_id = response.json()["document_id"]

        with patch("domain.capabilities.extract_document.process_pdf_document", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = ExtractionResult(
                extracted_text="--- Page 1 ---\nPage 1 text\n\n--- Page 2 ---\nPage 2 text",
                extraction_method="vision_escalation",
                confidence=0.88,
                warnings=["Escalation triggered: handwriting_detected"],
                signals=QualitySignals(0.7, True, 0.8, False),
                processing_time_ms=1000,
            )

            input_data = ExtractDocumentInput(document_id=doc_id)
            result = await execute_extract_document(input_data)

        assert isinstance(result, ExtractDocumentOutput)
        assert result.extraction_method == "vision_escalation"
        assert "Page 1" in result.extracted_text
        assert "Page 2" in result.extracted_text

    @pytest.mark.asyncio
    async def test_execute_extract_document_corrupt_file(self, temp_db):
        """Corrupt/unreadable file → ExtractDocumentError with failed status."""
        doc_id = create_document(
            filename="corrupt.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="corrupt.png",
        )

        # Mock file existence
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 1000

                # Mock pipeline to raise exception
                with patch("domain.capabilities.extract_document.process_document", new_callable=AsyncMock) as mock_process:
                    mock_process.side_effect = Exception("OCR failed: Cannot read file")

                    input_data = ExtractDocumentInput(document_id=doc_id)

                    with pytest.raises(ExtractDocumentError) as exc_info:
                        await execute_extract_document(input_data)

        assert exc_info.value.status == "failed"
        assert "extraction pipeline failed" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_execute_extract_document_not_found(self, temp_db):
        """Nonexistent document → ExtractDocumentError."""
        from backend.utils.ids import new_id
        fake_id = new_id()

        input_data = ExtractDocumentInput(document_id=fake_id)

        with pytest.raises(ExtractDocumentError) as exc_info:
            await execute_extract_document(input_data)

        assert exc_info.value.status == "failed"
        assert "not found" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_execute_extract_document_oversize(self, temp_db):
        """Document exceeding max size → ExtractDocumentError."""
        doc_id = create_document(
            filename="large.png",
            content_type="image/png",
            size_bytes=20 * 1024 * 1024,  # 20MB > 10MB limit
            storage_path="large.png",
        )

        # Mock file existence and size
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 20 * 1024 * 1024

                input_data = ExtractDocumentInput(document_id=doc_id)

                with pytest.raises(ExtractDocumentError) as exc_info:
                    await execute_extract_document(input_data)

        assert exc_info.value.status == "failed"
        assert "exceeds maximum" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_execute_extract_document_disallowed_mime(self, temp_db):
        """Document with disallowed MIME type → ExtractDocumentError."""
        doc_id = create_document(
            filename="test.txt",
            content_type="text/plain",
            size_bytes=1000,
            storage_path="test.txt",
        )

        # Mock file existence
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 1000

                input_data = ExtractDocumentInput(document_id=doc_id)

                with pytest.raises(ExtractDocumentError) as exc_info:
                    await execute_extract_document(input_data)

        assert exc_info.value.status == "failed"
        assert "unsupported file type" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_output_validates_against_schema(self, temp_db, uploaded_document):
        """Return value validates against ExtractDocumentOutput schema."""
        with patch("domain.capabilities.extract_document.process_document", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = ExtractionResult(
                extracted_text="Test text",
                extraction_method="vision_escalation",
                confidence=0.85,
                warnings=["Low confidence"],
                signals=QualitySignals(0.6, True, 0.7, False),
                processing_time_ms=500,
            )

            input_data = ExtractDocumentInput(document_id=uploaded_document)
            result = await execute_extract_document(input_data)

        # Validate all required fields present
        assert hasattr(result, "extracted_text")
        assert hasattr(result, "extraction_method")
        assert hasattr(result, "confidence")
        assert hasattr(result, "warnings")
        assert result.extraction_method in ("ocr", "vision_escalation")
        assert isinstance(result.confidence, float)
        assert isinstance(result.warnings, list)

    @pytest.mark.asyncio
    async def test_signals_only_in_debug_artifact_not_return_value(self, temp_db, uploaded_document):
        """The signals block is only in debug artifact, not in capability return value."""
        with patch("domain.capabilities.extract_document.process_document", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = ExtractionResult(
                extracted_text="Test text",
                extraction_method="ocr",
                confidence=0.9,
                warnings=[],
                signals=QualitySignals(0.9, False, 0.95, False),
                processing_time_ms=500,
            )

            input_data = ExtractDocumentInput(document_id=uploaded_document)
            result = await execute_extract_document(input_data)

        # Verify signals not in output
        output_dict = result.model_dump()
        assert "signals" not in output_dict
        assert "mean_ocr_confidence" not in output_dict
        assert "handwriting_detected" not in output_dict
        assert "completeness_estimate" not in output_dict
        assert "layout_complexity_flag" not in output_dict


# ============================================================================
# Debug Artifact Tests
# ============================================================================

class TestDebugArtifact:
    """Tests for the debug artifact written to data/extraction/{document_id}.json."""

    @pytest.mark.asyncio
    async def test_debug_artifact_written_with_full_signals(self, temp_db):
        """Debug artifact contains all signals fields per document-processing.md format."""
        doc_id = create_document(
            filename="artifact_test.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="artifact_test.png",
        )

        with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
            mock_ocr.return_value = OCRResult(
                full_text="Test content",
                regions=[
                    OCRRegion(text="Test content", confidence=0.9, bbox=[[0,0],[80,0],[80,20],[0,20]], region_type="text"),
                ],
                mean_confidence=0.9,
                processing_time_ms=100,
                page_count=1,
                layout_analysis={
                    'estimated_text_area': 0.12,
                    'region_density': 1.5,
                    'column_structure': [],
                    'table_regions': 0,
                },
            )

            with patch("domain.document_processing.pipeline.escalate_to_vision", new_callable=AsyncMock):
                await process_document(doc_id, "fake_path.png")

        # Check debug artifact exists and has correct format
        from backend.utils.paths import extraction_path
        artifact_path = extraction_path(doc_id).with_suffix(".json")

        assert artifact_path.exists()

        import json
        with open(artifact_path) as f:
            artifact = json.load(f)

        assert set(artifact.keys()) == set(ARTIFACT_KEYS)
        assert artifact["document_id"] == doc_id
        assert artifact["extraction_method"] in ("ocr", "vision_escalation")
        assert "extracted_text" in artifact
        assert "confidence" in artifact
        assert set(artifact["signals"].keys()) == set(SIGNAL_KEYS)
        assert "warnings" in artifact
        assert "processed_at" in artifact
        assert "layout_analysis" not in artifact
        assert "page_count" not in artifact

    @pytest.mark.asyncio
    async def test_debug_artifact_single_file_for_pdf(self, temp_db):
        """PDF processing writes only data/extraction/{document_id}.json."""
        doc_id = create_document(
            filename="one_artifact.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            storage_path="one_artifact.pdf",
        )
        from backend.utils.paths import EXTRACTION_ROOT, extraction_path

        with patch("domain.document_processing.pipeline.extract_pdf_pages") as mock_extract:
            mock_extract.return_value = ["page1.png"]
            with patch("domain.document_processing.pipeline.run_ocr") as mock_ocr:
                mock_ocr.return_value = OCRResult(
                    full_text="Only page",
                    regions=[
                        OCRRegion(
                            text="Only page",
                            confidence=0.95,
                            bbox=[[0, 0], [80, 0], [80, 20], [0, 20]],
                            region_type="text",
                        )
                    ],
                    mean_confidence=0.95,
                    processing_time_ms=40,
                    page_count=1,
                    layout_analysis={
                        "estimated_text_area": 0.12,
                        "region_density": 1.5,
                        "column_structure": [],
                        "table_regions": 0,
                    },
                )
                with patch(
                    "domain.document_processing.pipeline.escalate_to_vision",
                    new_callable=AsyncMock,
                ):
                    await process_pdf_document(doc_id, "fake.pdf")

        expected = extraction_path(doc_id).with_suffix(".json")
        assert expected.exists()
        extras = list(EXTRACTION_ROOT.glob(f"{doc_id}_page_*.json"))
        assert extras == []


# ============================================================================
# Timeout Configuration Tests
# ============================================================================

class TestTimeouts:
    """Tests for OCR 60s and total 120s enforcement."""

    def test_ocr_timeout_config(self):
        assert settings.capabilities.extract_document.timeout_seconds == 120
        assert OCR_PASS_TIMEOUT_SECONDS == 60

    @pytest.mark.asyncio
    async def test_ocr_pass_timeout_fails_capability_path(self, temp_db):
        """OCR exceeding the pass budget raises OCRTimeoutError."""
        import time as time_mod

        doc_id = create_document(
            filename="slow.png",
            content_type="image/png",
            size_bytes=1000,
            storage_path="slow.png",
        )

        def _slow_ocr(_path: str):
            time_mod.sleep(0.25)
            return OCRResult(
                full_text="late",
                regions=[],
                mean_confidence=0.9,
                processing_time_ms=250,
                page_count=1,
            )

        with patch("domain.document_processing.pipeline.OCR_PASS_TIMEOUT_SECONDS", 0.05):
            with patch("domain.document_processing.pipeline.run_ocr", side_effect=_slow_ocr):
                with pytest.raises(OCRTimeoutError):
                    await process_document(doc_id, "fake_path.png")


class TestContractSurface:
    def test_no_orchestrator_visible_vision_capability(self):
        registry = CapabilityRegistry(settings.capabilities)
        names = [entry.name for entry in registry.all()]
        assert "extract_document" in names
        assert "vision" not in names
        assert "extract_basic" not in names
        assert "escalate_to_vision" not in names

    def test_handwriting_not_inferred_from_low_confidence(self):
        bbox = [[0, 0], [80, 0], [80, 20], [0, 20]]
        assert _region_type_from_layout("", bbox) == "text"
        assert _region_type_from_layout("handwriting", bbox) == "handwriting"
        assert _region_type_from_layout("table", bbox) == "table"

    @pytest.mark.asyncio
    async def test_pdf_unreadable_fails(self, temp_db):
        doc_id = create_document(
            filename="bad.pdf",
            content_type="application/pdf",
            size_bytes=100,
            storage_path="bad.pdf",
        )
        with patch(
            "domain.document_processing.pipeline.extract_pdf_pages",
            return_value=[],
        ):
            with pytest.raises(UnreadableDocumentError):
                await process_pdf_document(doc_id, "fake.pdf")


class TestNormalizeBboxPaddle3x:
    """Regression: PaddleOCR 3.x returns numpy arrays for polys
    (rec_polys entries are (4,2) ndarrays, rec_boxes is (N,4)) — the old
    parser raised "only length-1 arrays can be converted to Python scalars"
    on every real extraction (observed live 2026-09-12, Workflow A)."""

    def test_numpy_polygon_4x2(self):
        import numpy as np

        poly = np.array([[24, 9], [695, 9], [695, 45], [24, 45]])
        bbox = _normalize_bbox(poly)
        assert bbox == [[24, 9], [695, 9], [695, 45], [24, 45]]

    def test_numpy_boxes_nx4_takes_first_row(self):
        import numpy as np

        boxes = np.array([[10, 20, 30, 40], [50, 60, 70, 80]])
        bbox = _normalize_bbox(boxes)
        assert bbox == [[10, 20], [30, 20], [30, 40], [10, 40]]

    def test_numpy_flat_box_4(self):
        import numpy as np

        bbox = _normalize_bbox(np.array([10.0, 20.0, 30.0, 40.0]))
        assert bbox == [[10, 20], [30, 20], [30, 40], [10, 40]]

    def test_python_nested_points(self):
        bbox = _normalize_bbox([[1, 2], [3, 4]])
        assert bbox == [[1, 2], [3, 4]]

    def test_python_flat_four(self):
        bbox = _normalize_bbox([1.0, 2.0, 3.0, 4.0])
        assert bbox == [[1, 2], [3, 2], [3, 4], [1, 4]]

    def test_uninterpretable_returns_empty_not_raises(self):
        assert _normalize_bbox(None) == []
        assert _normalize_bbox("not-a-box") == []
        assert _normalize_bbox([]) == []

    def test_parse_predict_mapping_with_numpy_polys(self):
        """Full 3.x-shaped result parses without scalar-conversion errors."""
        import numpy as np

        engine = OCREngine()
        raw = {
            "rec_texts": ["TRISHUL THERMAL POWER STATION", "8.3 mm/s RMS"],
            "rec_scores": [0.99, 0.97],
            "rec_polys": [
                np.array([[24, 9], [695, 9], [695, 45], [24, 45]]),
                np.array([[30, 100], [400, 100], [400, 130], [30, 130]]),
            ],
        }
        regions = engine._parse_predict_mapping(raw)
        assert len(regions) == 2
        assert regions[0].text == "TRISHUL THERMAL POWER STATION"
        assert regions[0].confidence == pytest.approx(0.99)
        assert regions[0].bbox == [[24, 9], [695, 9], [695, 45], [24, 45]]
        assert regions[1].text == "8.3 mm/s RMS"
        assert regions[1].bbox[0] == [30, 100]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])