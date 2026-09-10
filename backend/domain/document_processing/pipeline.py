"""Document processing pipeline with tiered OCR → vision escalation.

docs/document-processing.md:
1. Primary OCR pass (always)
2. Four quality signals (not a single confidence number)
3. Per-image escalation when any configured threshold is crossed
4. Vision pass via the `vision` resource
5. Result assembly + debug artifact at data/extraction/{document_id}.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional

from backend.config import settings
from backend.domain.document_processing.ocr import (
    OCR_PASS_TIMEOUT_SECONDS,
    OCRResult,
    extract_pdf_pages,
    run_ocr,
)
from backend.domain.document_processing.vision_escalation import escalate_to_vision
from backend.utils.paths import extraction_path

logger = logging.getLogger(__name__)

ARTIFACT_KEYS = (
    "document_id",
    "extraction_method",
    "extracted_text",
    "confidence",
    "signals",
    "warnings",
    "processed_at",
)
SIGNAL_KEYS = (
    "mean_ocr_confidence",
    "handwriting_detected",
    "completeness_estimate",
    "layout_complexity_flag",
)


class UnreadableDocumentError(Exception):
    """Corrupt or unreadable input — executor must return status=failed."""


class OCRTimeoutError(Exception):
    """OCR pass exceeded OCR_PASS_TIMEOUT_SECONDS."""


class PipelineTimeoutError(Exception):
    """Total extract_document budget (config timeout_seconds) exhausted."""


@dataclass
class QualitySignals:
    mean_ocr_confidence: float
    handwriting_detected: bool
    completeness_estimate: float
    layout_complexity_flag: bool


@dataclass
class ExtractionResult:
    extracted_text: str
    extraction_method: str
    confidence: float
    warnings: List[str]
    signals: QualitySignals
    processing_time_ms: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _total_timeout_seconds() -> float:
    return float(settings.capabilities.extract_document.timeout_seconds)


def assess_quality(ocr_result: OCRResult) -> QualitySignals:
    """Four independent signals (docs/document-processing.md step 2)."""
    if not ocr_result.regions:
        return QualitySignals(
            mean_ocr_confidence=ocr_result.mean_confidence,
            handwriting_detected=False,
            completeness_estimate=0.0,
            layout_complexity_flag=False,
        )

    mean_confidence = ocr_result.mean_confidence
    handwriting_detected = any(r.region_type == "handwriting" for r in ocr_result.regions)

    # Completeness is layout density, never a restatement of OCR confidence.
    if ocr_result.layout_analysis:
        layout = ocr_result.layout_analysis
        estimated_text_area = float(layout.get("estimated_text_area", 0.0))
        region_density = float(layout.get("region_density", 0.0))
        expected_min_coverage = 0.05
        expected_min_density = 0.5
        coverage_score = min(estimated_text_area / expected_min_coverage, 1.0)
        density_score = min(region_density / expected_min_density, 1.0)
        if len(layout.get("column_structure") or []) > 1:
            density_score = min(density_score * 1.2, 1.0)
        completeness_estimate = (coverage_score + density_score) / 2
    else:
        completeness_estimate = 0.0

    table_regions = sum(1 for r in ocr_result.regions if r.region_type == "table")
    vertical_regions = sum(1 for r in ocr_result.regions if r.region_type == "vertical_text")
    multi_column = False
    if ocr_result.layout_analysis:
        multi_column = len(ocr_result.layout_analysis.get("column_structure") or []) > 1
    layout_complexity_flag = table_regions > 0 or vertical_regions > 2 or multi_column

    return QualitySignals(
        mean_ocr_confidence=mean_confidence,
        handwriting_detected=handwriting_detected,
        completeness_estimate=completeness_estimate,
        layout_complexity_flag=layout_complexity_flag,
    )


def should_escalate(signals: QualitySignals) -> tuple[bool, List[str]]:
    thresholds = settings.app.ocr.escalation_thresholds
    triggered: List[str] = []

    if signals.mean_ocr_confidence < thresholds.mean_confidence_below:
        triggered.append(
            f"mean_confidence_below ({signals.mean_ocr_confidence:.2f} < {thresholds.mean_confidence_below})"
        )
    if signals.completeness_estimate < thresholds.completeness_below:
        triggered.append(
            f"completeness_below ({signals.completeness_estimate:.2f} < {thresholds.completeness_below})"
        )
    if thresholds.handwriting_detected and signals.handwriting_detected:
        triggered.append("handwriting_detected")
    if thresholds.layout_complexity_flag and signals.layout_complexity_flag:
        triggered.append("layout_complexity_flag")

    return len(triggered) > 0, triggered


def _prepare_flagged_regions(ocr_result: OCRResult) -> List[dict]:
    flagged = []
    for region in ocr_result.regions:
        if region.region_type in ("handwriting", "table", "vertical_text") or region.confidence < 0.6:
            flagged.append(
                {
                    "region_type": region.region_type,
                    "confidence": region.confidence,
                    "bbox": region.bbox,
                    "text_preview": region.text[:100] if region.text else "",
                }
            )
    return flagged


def _write_debug_artifact(document_id: str, result: ExtractionResult) -> None:
    """Write exactly the docs/document-processing.md extraction artifact keys."""
    artifact_path = extraction_path(document_id).with_suffix(".json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_id": document_id,
        "extraction_method": result.extraction_method,
        "extracted_text": result.extracted_text,
        "confidence": result.confidence,
        "signals": {key: asdict(result.signals)[key] for key in SIGNAL_KEYS},
        "warnings": result.warnings,
        "processed_at": _now_iso(),
    }
    artifact = {key: payload[key] for key in ARTIFACT_KEYS}
    with open(artifact_path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2)
    logger.debug("Wrote debug artifact to %s", artifact_path)


async def _ocr_with_timeout(image_path: str, timeout_seconds: float) -> OCRResult:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(run_ocr, image_path),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise OCRTimeoutError(
            f"OCR pass exceeded {OCR_PASS_TIMEOUT_SECONDS}s for {image_path}"
        ) from exc


async def _process_one_image(
    image_path: str,
    job_id: Optional[str],
    deadline: float,
) -> ExtractionResult:
    """Tiered pipeline for a single image. Does not write the debug artifact."""
    start_time = time.perf_counter()
    warnings: List[str] = []

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PipelineTimeoutError("extract_document total timeout exhausted before OCR")

    ocr_budget = min(float(OCR_PASS_TIMEOUT_SECONDS), remaining)
    try:
        ocr_result = await _ocr_with_timeout(image_path, ocr_budget)
    except OCRTimeoutError:
        raise
    except Exception as exc:
        raise UnreadableDocumentError(f"OCR failed: {exc}") from exc

    signals = assess_quality(ocr_result)
    logger.info(
        "OCR quality signals: mean_conf=%.2f handwriting=%s completeness=%.2f layout_complex=%s",
        signals.mean_ocr_confidence,
        signals.handwriting_detected,
        signals.completeness_estimate,
        signals.layout_complexity_flag,
    )

    escalate, triggered_signals = should_escalate(signals)
    extraction_method = "ocr"
    final_text = ocr_result.full_text
    confidence = signals.mean_ocr_confidence

    if escalate:
        warnings.append(f"Escalation triggered: {', '.join(triggered_signals)}")
        remaining = deadline - time.monotonic()
        vision_text = ""
        if remaining <= 0:
            warnings.append(
                "Vision escalation needed but unavailable (total timeout exhausted); using OCR result"
            )
        else:
            flagged = _prepare_flagged_regions(ocr_result)
            try:
                vision_text = await asyncio.wait_for(
                    escalate_to_vision(image_path, flagged, job_id),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                vision_text = ""
                warnings.append(
                    "Vision escalation needed but timed out; using OCR result"
                )

        if vision_text:
            final_text = vision_text
            extraction_method = "vision_escalation"
            if confidence < settings.app.ocr.escalation_thresholds.mean_confidence_below:
                warnings.append(
                    f"extraction confidence remains low ({confidence:.2f}) even after vision escalation"
                )
        else:
            if not any("unavailable" in w.lower() or "timed out" in w.lower() for w in warnings):
                warnings.append(
                    "Vision escalation needed but vision model unavailable; using OCR result"
                )

    if not (final_text or "").strip():
        warnings.append("No text extracted from document")

    return ExtractionResult(
        extracted_text=final_text,
        extraction_method=extraction_method,
        confidence=confidence,
        warnings=warnings,
        signals=signals,
        processing_time_ms=int((time.perf_counter() - start_time) * 1000),
    )


async def process_document(
    document_id: str,
    image_path: str,
    job_id: Optional[str] = None,
) -> ExtractionResult:
    deadline = time.monotonic() + _total_timeout_seconds()
    result = await _process_one_image(image_path, job_id, deadline)
    _write_debug_artifact(document_id, result)
    logger.info(
        "Document %s processed: method=%s confidence=%.2f warnings=%s",
        document_id,
        result.extraction_method,
        result.confidence,
        len(result.warnings),
    )
    return result


def _aggregate_page_results(page_results: List[ExtractionResult]) -> ExtractionResult:
    all_text = []
    all_warnings: List[str] = []
    all_signals: List[QualitySignals] = []
    total_time = 0
    methods = set()
    for i, page_result in enumerate(page_results):
        all_text.append(f"--- Page {i + 1} ---\n{page_result.extracted_text}")
        all_warnings.extend(page_result.warnings)
        all_signals.append(page_result.signals)
        total_time += page_result.processing_time_ms
        methods.add(page_result.extraction_method)

    if all_signals:
        aggregated = QualitySignals(
            mean_ocr_confidence=min(s.mean_ocr_confidence for s in all_signals),
            handwriting_detected=any(s.handwriting_detected for s in all_signals),
            completeness_estimate=min(s.completeness_estimate for s in all_signals),
            layout_complexity_flag=any(s.layout_complexity_flag for s in all_signals),
        )
        overall_confidence = min(s.mean_ocr_confidence for s in all_signals)
    else:
        aggregated = QualitySignals(0.0, False, 0.0, False)
        overall_confidence = 0.0

    return ExtractionResult(
        extracted_text="\n\n".join(all_text),
        extraction_method="vision_escalation" if "vision_escalation" in methods else "ocr",
        confidence=overall_confidence,
        warnings=all_warnings,
        signals=aggregated,
        processing_time_ms=total_time,
    )


async def process_multi_page_document(
    document_id: str,
    image_paths: List[str],
    job_id: Optional[str] = None,
) -> ExtractionResult:
    """Process page images independently; write one debug artifact for document_id."""
    if not image_paths:
        raise UnreadableDocumentError("No page images to process")

    deadline = time.monotonic() + _total_timeout_seconds()
    page_results: List[ExtractionResult] = []
    for path in image_paths:
        page_results.append(await _process_one_image(path, job_id, deadline))

    result = _aggregate_page_results(page_results)
    _write_debug_artifact(document_id, result)
    return result


async def process_pdf_document(
    document_id: str,
    pdf_path: str,
    job_id: Optional[str] = None,
) -> ExtractionResult:
    import tempfile

    with tempfile.TemporaryDirectory(prefix=f"pdf_pages_{document_id}_") as tmpdir:
        try:
            page_images = extract_pdf_pages(pdf_path, tmpdir)
        except Exception as exc:
            raise UnreadableDocumentError(f"Failed to extract PDF pages: {exc}") from exc
        if not page_images:
            raise UnreadableDocumentError(f"No pages extracted from PDF: {pdf_path}")
        return await process_multi_page_document(document_id, page_images, job_id)
