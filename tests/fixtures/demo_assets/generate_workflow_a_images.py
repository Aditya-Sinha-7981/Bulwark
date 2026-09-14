#!/usr/bin/env python3
"""Regenerate the Workflow A synthetic inspection-report images
(tests/fixtures/demo_assets/workflow_a/*.png) — tasks/19-sih-workflow-validation.md
§7 Requirement 1.

Two variants of the same synthetic content (Pump P-104, SOP-100): a clean
single-pass OCR case, and a degraded case tuned to trip the completeness_below
escalation threshold (config/app.yaml ocr.escalation_thresholds) without
degrading so far that PaddleOCR detects zero regions (a real edge case found
while tuning this asset — backend/domain/document_processing/ocr.py's
`_parse_predict_mapping` raises ValueError on an empty numpy array from
`mapping.get(...) or ...`, rather than failing gracefully; routed to the
document-processing owner, not fixed here per this task's scope).

Usage:
    python tests/fixtures/demo_assets/generate_workflow_a_images.py
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).resolve().parent / "workflow_a"

W, H = 1240, 1600  # roughly A4 at 150dpi

REPORT_LINES = [
    "INSPECTION REPORT",
    "",
    "Facility: Process Water Loop - Area 4",
    "Equipment ID: Pump P-104 (Centrifugal, SOP-100)",
    "Inspector: J. Rao      Date: 2026-09-10      Shift: Day",
    "",
    "Readings observed during routine inspection:",
    "",
    "  Discharge pressure:      5.1 bar",
    "  Bearing temperature:     92 degrees C",
    "  Vibration velocity:      3.8 mm/s RMS",
    "  Seal leakage:            none observed",
    "  Suction noise:           normal, no cavitation detected",
    "",
    "Notes:",
    "Bearing temperature reading is elevated compared to the previous",
    "inspection (81 C, logged 2026-08-11). No visible leakage or unusual",
    "vibration. Recommend maintenance review per applicable SOP before",
    "returning to unattended operation.",
    "",
    "Signature: J. Rao",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_clean(path: Path) -> None:
    img = Image.new("L", (W, H), color=255)
    draw = ImageDraw.Draw(img)
    font_title = _font(34)
    font_body = _font(24)

    y = 80
    for i, line in enumerate(REPORT_LINES):
        f = font_title if i == 0 else font_body
        draw.text((90, y), line, fill=0, font=f)
        y += 42 if i == 0 else 36

    img.convert("RGB").save(path, "PNG")


def make_degraded(path: Path) -> None:
    """Same content, deliberately degraded to trip the completeness_below
    escalation threshold: a small, low-contrast, noised text block on an
    otherwise blank page (low layout coverage) with light blur/rotation.
    Verified against the real OCR pipeline: mean_confidence ~0.91,
    completeness_estimate ~0.49 (< 0.6 threshold) → escalates; zero crashes."""
    img = Image.new("L", (W, H), color=238)
    draw = ImageDraw.Draw(img)
    font_title = _font(14)
    font_body = _font(11)

    y = 60
    for i, line in enumerate(REPORT_LINES):
        f = font_title if i == 0 else font_body
        draw.text((60, y), line, fill=140, font=f)
        y += 20 if i == 0 else 16

    random.seed(19)
    pixels = img.load()
    for _ in range(int(W * H * 0.08)):
        x = random.randrange(W)
        yy = random.randrange(H)
        pixels[x, yy] = max(0, min(255, pixels[x, yy] + random.randint(-70, 70)))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    img = img.rotate(4.0, expand=True, fillcolor=238)
    img.convert("RGB").save(path, "PNG")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_clean(OUT_DIR / "clean_inspection_report.png")
    make_degraded(OUT_DIR / "degraded_inspection_report.png")
    print(f"wrote {OUT_DIR}/clean_inspection_report.png and degraded_inspection_report.png")
