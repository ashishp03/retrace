"""Stage 3 — OCR gate. Tesseract over metadata-gate survivors; drop anything under the
confident-word threshold (start at 8, per ../CLAUDE.md).

`ocr_text` is kept regardless of pass/fail — reused as a stage-4 hint and as search fallback.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import pytesseract
from PIL import Image, ImageOps
from pathlib import Path

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
MIN_CONFIDENT_WORDS = 6  # CLAUDE.md's stated starting point was 8; lowered after needle
                          # screenshot_03 (a genuine 7-word short text) showed 8 was too strict
MIN_WORD_CONFIDENCE = 40  # tesseract per-word confidence, 0-100


@dataclass
class OcrResult:
    path: Path
    passed: bool
    confident_word_count: int
    ocr_text: str


CONTENT_CROP_PADDING_PX = 20
BACKGROUND_DIFF_THRESHOLD = 15


def _prepare_for_ocr(img: Image.Image) -> Image.Image:
    """Grayscale, auto-invert light-text-on-dark-background images (e.g. dark-mode
    screenshots) since tesseract assumes dark text on a light background, then crop to the
    actual content bounding box.

    The crop matters more than it looks: tesseract's automatic page-layout analysis can drop
    entire text blocks on images that are mostly blank margin around a small amount of content
    (e.g. a screenshot of one short text message on an otherwise empty screen) — found by
    running this gate against needle screenshot_03, which returned only the app-bar text until
    cropped to content first. Feeding it a tightly-cropped, bordered image sidesteps that
    layout-analysis failure mode entirely, and is cheap since gate images are already small.
    """
    gray = ImageOps.grayscale(img)
    mean = sum(i * c for i, c in enumerate(gray.histogram())) / max(1, gray.width * gray.height)
    if mean < 128:
        gray = ImageOps.invert(gray)

    bg_value = gray.getpixel((gray.width - 1, gray.height - 1))
    mask = gray.point(lambda p: 255 if abs(p - bg_value) > BACKGROUND_DIFF_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return gray  # no content detected at all — let the word count decide, not this step

    x0, y0, x1, y1 = bbox
    pad = CONTENT_CROP_PADDING_PX
    cropped = gray.crop((
        max(0, x0 - pad), max(0, y0 - pad),
        min(gray.width, x1 + pad), min(gray.height, y1 + pad),
    ))
    return ImageOps.expand(cropped, border=pad, fill=int(bg_value))


def check_ocr(path: Path) -> OcrResult:
    with Image.open(path) as img:
        prepared = _prepare_for_ocr(img)
        data = pytesseract.image_to_data(prepared, output_type=pytesseract.Output.DICT)

    words: list[str] = []
    confident_count = 0
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        if not text:
            continue
        words.append(text)
        try:
            if float(conf) >= MIN_WORD_CONFIDENCE:
                confident_count += 1
        except ValueError:
            pass

    ocr_text = " ".join(words)
    return OcrResult(path=path, passed=confident_count >= MIN_CONFIDENT_WORDS,
                      confident_word_count=confident_count, ocr_text=ocr_text)


def run(paths: list[Path]) -> list[OcrResult]:
    return [check_ocr(p) for p in paths]


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "tests/needles/docs"
    paths = sorted(p for p in target.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    start = time.perf_counter()
    results = run(paths)
    elapsed = time.perf_counter() - start

    passed = sum(r.passed for r in results)
    per_image_ms = (elapsed / len(paths) * 1000) if paths else 0.0
    print(f"{passed}/{len(paths)} passed OCR gate in {elapsed * 1000:.1f}ms ({per_image_ms:.2f}ms/image)")
    for r in results:
        status = "PASS" if r.passed else "DROP"
        preview = r.ocr_text[:50].replace("\n", " ")
        print(f"  {status}  {r.path.name:<24} words={r.confident_word_count:<3} '{preview}'")
