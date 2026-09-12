"""PaddleOCR PP-OCRv6 wrapper for document text extraction.

Primary OCR pass for extract_document. Runs on every document, every time
(docs/document-processing.md step 1).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from PIL import Image

logger = logging.getLogger(__name__)

OCR_PASS_TIMEOUT_SECONDS = 60


@dataclass
class OCRRegion:
    """A single detected text region from PaddleOCR."""

    text: str
    confidence: float
    bbox: List[List[int]]
    region_type: str
    layout_score: Optional[float] = None


@dataclass
class OCRResult:
    """Result of the primary OCR pass."""

    full_text: str
    regions: List[OCRRegion]
    mean_confidence: float
    processing_time_ms: int
    page_count: int
    layout_analysis: Optional[dict] = None


class OCREngine:
    """PaddleOCR PP-OCRv6 engine wrapper (CPU)."""

    _instance: Optional["OCREngine"] = None

    def __init__(self) -> None:
        self._ocr = None
        self._initialized = False

    def _initialize(self) -> None:
        if self._initialized:
            return
        try:
            from paddleocr import PaddleOCR

            # PaddleOCR 3.x: no use_gpu / use_angle_cls. CPU is the default.
            try:
                self._ocr = PaddleOCR(lang="en", use_textline_orientation=True)
            except TypeError:
                self._ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)
            self._initialized = True
            logger.info("PaddleOCR initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize PaddleOCR: %s", exc)
            raise

    def extract(self, image_path: str) -> OCRResult:
        self._initialize()
        start_time = time.perf_counter()
        try:
            raw = self._run_engine(image_path)
        except Exception as exc:
            logger.error("OCR failed for %s: %s", image_path, exc)
            raise

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        regions = self._parse_regions(raw)
        confidences = [r.confidence for r in regions]
        full_text = "\n".join(r.text for r in regions if r.text)
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        layout_analysis = self._analyze_layout(regions, image_path)

        return OCRResult(
            full_text=full_text,
            regions=regions,
            mean_confidence=mean_confidence,
            processing_time_ms=elapsed_ms,
            page_count=max(self._page_count(raw), 1),
            layout_analysis=layout_analysis,
        )

    def _run_engine(self, image_path: str) -> Any:
        """Call the installed PaddleOCR API (3.x predict() or 2.x ocr())."""
        if hasattr(self._ocr, "predict"):
            try:
                return self._ocr.predict(image_path)
            except TypeError:
                pass
        try:
            return self._ocr.ocr(image_path)
        except TypeError:
            return self._ocr.ocr(image_path, cls=True)

    def _page_count(self, raw: Any) -> int:
        if raw is None:
            return 1
        if isinstance(raw, list):
            return max(len(raw), 1)
        return 1

    def _parse_regions(self, raw: Any) -> List[OCRRegion]:
        if not raw:
            return []

        regions: List[OCRRegion] = []
        pages = raw if isinstance(raw, list) else [raw]
        for page in pages:
            regions.extend(self._parse_page(page))
        return regions

    def _parse_page(self, page: Any) -> List[OCRRegion]:
        mapping = _as_mapping(page)
        if mapping and ("rec_texts" in mapping or "rec_text" in mapping):
            return self._parse_predict_mapping(mapping)

        if not page:
            return []
        if isinstance(page, list):
            regions: List[OCRRegion] = []
            for line in page:
                parsed = self._parse_legacy_line(line)
                if parsed is not None:
                    regions.append(parsed)
            return regions
        return []

    def _parse_predict_mapping(self, mapping: dict) -> List[OCRRegion]:
        texts = mapping.get("rec_texts") or mapping.get("rec_text") or []
        scores = mapping.get("rec_scores") or mapping.get("rec_score") or []
        polys = mapping.get("rec_polys") or mapping.get("dt_polys") or mapping.get("rec_boxes") or []
        layout_labels = _layout_labels(mapping)

        regions: List[OCRRegion] = []
        for i, text in enumerate(texts):
            confidence = float(scores[i]) if i < len(scores) else 0.0
            bbox = _normalize_bbox(polys[i] if i < len(polys) else [])
            label, layout_score = _label_for_index(layout_labels, i, bbox)
            region_type = _region_type_from_layout(label, bbox)
            regions.append(
                OCRRegion(
                    text=str(text),
                    confidence=confidence,
                    bbox=bbox,
                    region_type=region_type,
                    layout_score=layout_score,
                )
            )
        return regions

    def _parse_legacy_line(self, line: Any) -> Optional[OCRRegion]:
        if not line or not isinstance(line, (list, tuple)) or len(line) < 2:
            return None
        bbox = _normalize_bbox(line[0])
        text_info = line[1]
        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
            text = str(text_info[0])
            confidence = float(text_info[1])
        elif isinstance(text_info, dict):
            text = str(text_info.get("text", ""))
            confidence = float(text_info.get("confidence", text_info.get("score", 0.0)))
        else:
            return None

        layout_type = ""
        layout_score = None
        if len(line) > 2 and isinstance(line[2], dict):
            layout_score = line[2].get("score")
            layout_type = str(line[2].get("type", "")).lower()

        region_type = _region_type_from_layout(layout_type, bbox)
        return OCRRegion(
            text=text,
            confidence=confidence,
            bbox=bbox,
            region_type=region_type,
            layout_score=layout_score,
        )

    def _analyze_layout(self, regions: List[OCRRegion], image_path: str) -> dict:
        empty = {
            "estimated_text_area": 0.0,
            "region_density": 0.0,
            "column_structure": [],
            "table_regions": 0,
        }
        if not regions:
            return empty

        with Image.open(image_path) as img:
            img_width, img_height = img.size
        image_area = img_width * img_height
        if image_area <= 0:
            return empty

        total_region_area = 0
        for region in regions:
            xs = [p[0] for p in region.bbox]
            ys = [p[1] for p in region.bbox]
            if not xs or not ys:
                continue
            total_region_area += (max(xs) - min(xs)) * (max(ys) - min(ys))

        estimated_text_area = total_region_area / image_area
        region_density = len(regions) / (image_area / 10000)
        column_structure = self._detect_columns(regions)
        table_regions = sum(1 for r in regions if r.region_type == "table")

        return {
            "estimated_text_area": estimated_text_area,
            "region_density": region_density,
            "column_structure": column_structure,
            "table_regions": table_regions,
            "image_width": img_width,
            "image_height": img_height,
        }

    def _detect_columns(self, regions: List[OCRRegion]) -> List[dict]:
        if len(regions) < 2:
            return []

        centers = []
        widths = []
        for region in regions:
            xs = [p[0] for p in region.bbox]
            if not xs:
                continue
            centers.append((min(xs) + max(xs)) / 2)
            widths.append(max(xs) - min(xs))
        if len(centers) < 2:
            return []

        centers.sort()
        avg_width = sum(widths) / len(widths) if widths else 0
        columns: List[dict] = []
        current = [centers[0]]
        for i in range(1, len(centers)):
            gap = centers[i] - centers[i - 1]
            if avg_width > 0 and gap > avg_width * 1.5:
                columns.append(
                    {"x_center": sum(current) / len(current), "region_count": len(current)}
                )
                current = [centers[i]]
            else:
                current.append(centers[i])
        if current:
            columns.append(
                {"x_center": sum(current) / len(current), "region_count": len(current)}
            )
        return columns


def _as_mapping(item: Any) -> Optional[dict]:
    if isinstance(item, dict):
        return item
    json_attr = getattr(item, "json", None)
    if callable(json_attr):
        try:
            data = json_attr()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if hasattr(item, "keys"):
        try:
            return {k: item[k] for k in item.keys()}
        except Exception:
            return None
    return None


def _layout_labels(mapping: dict) -> List[dict]:
    raw = mapping.get("layout_det_res") or mapping.get("layout_result") or []
    if isinstance(raw, dict):
        raw = raw.get("boxes") or raw.get("regions") or []
    labels = []
    for entry in raw or []:
        if isinstance(entry, dict):
            labels.append(entry)
    return labels


def _label_for_index(layout_labels: List[dict], index: int, bbox: List[List[int]]) -> tuple[str, Optional[float]]:
    if index < len(layout_labels):
        entry = layout_labels[index]
        label = str(entry.get("label") or entry.get("type") or "").lower()
        score = entry.get("score")
        return label, float(score) if score is not None else None
    return "", None


def _region_type_from_layout(layout_type: str, bbox: List[List[int]]) -> str:
    """Classify from layout labels only — never from OCR confidence (ADR-04)."""
    layout_type = (layout_type or "").lower()
    if layout_type in ("handwriting", "handwritten", "handwritten_text"):
        return "handwriting"
    if layout_type in ("table", "table_caption"):
        return "table"
    if layout_type in ("figure", "image", "chart"):
        return "figure"
    if bbox and len(bbox) >= 2:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if height > 0:
            aspect_ratio = width / height
            if aspect_ratio < 0.25 and height > 100:
                return "vertical_text"
    return "text"


def _normalize_bbox(raw: Any) -> List[List[int]]:
    """Normalize one OCR polygon/bbox into a list of [x, y] int points.

    Accepts numpy arrays (PaddleOCR 3.x `rec_polys`/`dt_polys` entries are
    (4, 2) ndarrays, `rec_boxes` rows are (4,) or (N, 4)), nested python
    sequences of [x, y] points, and flat sequences ([x1, y1, x2, y2, ...]
    or a 4-number bounding box). Returns [] when nothing is interpretable —
    never raises on unexpected shapes.
    """
    if raw is None:
        return []
    try:
        import numpy as np

        arr = np.asarray(raw, dtype=float)
    except Exception:
        arr = None

    if arr is not None:
        arr = np.squeeze(arr)
        # (4,2)/(N,2) polygon → [x, y] points
        if arr.ndim == 2 and arr.shape[1] == 2 and arr.shape[0] >= 2:
            return [[int(x), int(y)] for x, y in arr]
        # (N,4) batch of boxes or a (1,4) row → treat the first row as one
        # [x_min, y_min, x_max, y_max] bounding box (this helper receives a
        # single line's bbox; a batch reaching it means the caller fell back
        # to rec_boxes wholesale).
        if arr.ndim == 2 and arr.shape[1] == 4 and arr.size >= 4:
            x1, y1, x2, y2 = arr.reshape(-1)[:4]
            return [[int(x1), int(y1)], [int(x2), int(y1)], [int(x2), int(y2)], [int(x1), int(y2)]]
        # (4,) bounding box or (8,) flat polygon (single line)
        if arr.ndim == 1 and arr.size >= 4:
            if arr.size == 4:
                x1, y1, x2, y2 = arr
                return [[int(x1), int(y1)], [int(x2), int(y1)], [int(x2), int(y2)], [int(x1), int(y2)]]
            return [[int(arr[i]), int(arr[i + 1])] for i in range(0, arr.size - 1, 2)]
        return []

    # Non-numeric fallback: python sequences of points
    try:
        seq = list(raw)
    except TypeError:
        return []
    points: List[List[int]] = []
    for point in seq:
        try:
            points.append([int(float(point[0])), int(float(point[1]))])
        except (TypeError, IndexError, ValueError):
            continue
    return points


def get_ocr_engine() -> OCREngine:
    if OCREngine._instance is None:
        OCREngine._instance = OCREngine()
    return OCREngine._instance


def run_ocr(image_path: str) -> OCRResult:
    return get_ocr_engine().extract(image_path)


def extract_pdf_pages(pdf_path: str, output_dir: str) -> List[str]:
    """Render each scanned PDF page to a PNG. Raises on unreadable PDF."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("pypdfium2 is required to extract scanned PDF pages") from exc

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pdf = pdfium.PdfDocument(pdf_path)
    page_images: List[str] = []
    try:
        if len(pdf) == 0:
            raise RuntimeError(f"PDF has no pages: {pdf_path}")
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            page_path = output_path / f"page_{page_num + 1}.png"
            pil_image.save(page_path, format="PNG")
            page_images.append(str(page_path))
    finally:
        pdf.close()

    if not page_images:
        raise RuntimeError(f"Failed to extract pages from PDF: {pdf_path}")
    logger.info("Extracted %s pages from PDF: %s", len(page_images), pdf_path)
    return page_images
