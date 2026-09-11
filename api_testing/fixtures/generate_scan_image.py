"""Generate a synthetic "scanned inspection report" PNG for manual testing of
Workflow A (extract_document -> search_knowledge_base -> create_docx).

There is no real scanned-document fixture anywhere in the repo (checked at
the time this file was written), so this renders one on the fly instead of
committing a binary image to the repo.

Usage:
    python3 api_testing/fixtures/generate_scan_image.py
    # writes api_testing/fixtures/scan-clean.png and scan-degraded.png

Requires Pillow (already a transitive dependency of paddleocr, so it should
be present once backend/requirements.txt is installed; if not: pip install pillow).
"""
from __future__ import annotations

import random
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Pillow is required. It ships transitively with paddleocr "
        "(backend/requirements.txt); if that's not installed yet, "
        "run: pip install pillow"
    ) from exc

REPORT_TEXT = """\
INSPECTION REPORT

Facility: Zone 4 - Compressor House
Inspector: R. Mehta
Date: 2026-09-10

Findings:
1. Fire extinguisher FE-014-B pressure gauge reads below the green zone.
2. Tamper seal on FE-014-B is intact; unit last serviced 2025-08-02.
3. Bearing temperature on Compressor Unit C-3 measured at 78 C, within limits.
4. Minor lubricant discoloration observed on Pump P-2, flagged for review.

Recommendation:
Tag FE-014-B out of service pending recharge; schedule Pump P-2 lubricant
sampling within 7 days per maintenance SOP.
"""


def _font(size: int):
    for candidate in (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(text: str, out_path: Path, *, degrade: bool = False) -> None:
    width, height = 1240, 1754  # ~A4 at 150dpi
    img = Image.new("L", (width, height), color=250)
    draw = ImageDraw.Draw(img)
    font = _font(28)

    y = 100
    for line in text.split("\n"):
        draw.text((90, y), line, fill=20, font=font)
        y += 42

    if degrade:
        # Simulate a poor-quality scan: blur, noise, slight rotation.
        img = img.rotate(1.5, expand=False, fillcolor=250)
        img = img.filter(ImageFilter.GaussianBlur(radius=1.6))
        pixels = img.load()
        for _ in range(int(width * height * 0.02)):
            x = random.randrange(width)
            yy = random.randrange(height)
            pixels[x, yy] = random.choice([0, 255])

    img.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    render(REPORT_TEXT, out_dir / "scan-clean.png", degrade=False)
    render(REPORT_TEXT, out_dir / "scan-degraded.png", degrade=True)
