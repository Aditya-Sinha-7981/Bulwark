"""Vision escalation for document extraction.

Uses the `vision` resource type via Model Runtime (never a model name).
Failures return empty string so the pipeline can fall back to OCR
(docs/document-processing.md "Failures").
"""

from __future__ import annotations

import logging
from typing import List, Optional

from backend.domain.model_runtime.runtime import (
    ModelRuntimeError,
    ModelRuntimeUnavailableError,
    runtime as model_runtime,
)

logger = logging.getLogger(__name__)


VISION_EXTRACTION_PROMPT = """You are an expert document transcription system. Extract ALL text content from this image accurately.

Instructions:
1. Transcribe all visible text, including handwritten text, printed text, and text in tables/figures
2. Preserve the document structure - maintain paragraphs, line breaks, and reading order
3. For tables, extract as structured text with clear row/column separation
4. If text is illegible or unclear, mark with [ILLEGIBLE] but continue
5. Do NOT add commentary, analysis, or formatting beyond what's in the document
6. Output ONLY the extracted text content

Document image:"""


async def escalate_to_vision(
    image_path: str,
    flagged_regions: Optional[List[dict]] = None,
    job_id: Optional[str] = None,
) -> str:
    try:
        image_bytes = _read_image_bytes(image_path)
        prompt = _build_prompt(flagged_regions)
        result = await model_runtime.generate(
            resource_type="vision",
            prompt=prompt,
            images=[image_bytes],
            job_id=job_id,
        )
        logger.info(
            "Vision escalation completed for %s, %s chars extracted",
            image_path,
            len(result.text),
        )
        return result.text.strip()
    except (ModelRuntimeUnavailableError, ModelRuntimeError) as exc:
        logger.warning("Vision escalation unavailable for %s: %s", image_path, exc)
        return ""
    except Exception as exc:
        logger.error("Vision escalation failed unexpectedly for %s: %s", image_path, exc)
        return ""


def _read_image_bytes(image_path: str) -> bytes:
    with open(image_path, "rb") as handle:
        return handle.read()


def _build_prompt(flagged_regions: Optional[List[dict]]) -> str:
    prompt = VISION_EXTRACTION_PROMPT
    if flagged_regions:
        region_info = "\n\nFlagged regions requiring attention:\n"
        for i, region in enumerate(flagged_regions):
            region_type = region.get("region_type", "unknown")
            confidence = region.get("confidence", 0.0)
            bbox = region.get("bbox", [])
            region_info += (
                f"  Region {i + 1}: type={region_type}, "
                f"confidence={confidence:.2f}, bbox={bbox}\n"
            )
        prompt += region_info + "\nPay special attention to the flagged regions above."
    return prompt


async def escalate_multiple_pages(
    image_paths: List[str],
    flagged_regions_per_page: Optional[List[List[dict]]] = None,
    job_id: Optional[str] = None,
) -> List[str]:
    results = []
    for i, path in enumerate(image_paths):
        flagged = None
        if flagged_regions_per_page and i < len(flagged_regions_per_page):
            flagged = flagged_regions_per_page[i]
        results.append(await escalate_to_vision(path, flagged, job_id))
    return results
