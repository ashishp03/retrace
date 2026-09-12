"""Stage 2 — Metadata gate. Cheap, model-free filtering of obvious non-documents.

Loose by design (see ../CLAUDE.md): demotes, doesn't decide. A survivor here still has to pass
the OCR gate (stage 3) before it's ever considered for extraction (stage 4).
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".heic")
MIN_DIMENSION_PX = 100
MAX_ASPECT_RATIO = 3.0  # beyond this looks like a panorama/strip, not a document
FILENAME_HINTS = ("img_", "screenshot", "photo", "scan", "receipt", "doc")


@dataclass
class MetadataResult:
    path: Path
    passed: bool
    reasons: list[str] = field(default_factory=list)  # why demoted, or weak positive signals
    width: int = 0
    height: int = 0
    has_exif: bool = False
    filename_hint: bool = False


def check_metadata(path: Path) -> MetadataResult:
    try:
        with Image.open(path) as img:
            width, height = img.size
            has_exif = bool(img.getexif())
    except Exception as e:
        return MetadataResult(path=path, passed=False, reasons=[f"unreadable: {e}"])

    filename_hint = any(h in path.name.lower() for h in FILENAME_HINTS)

    if min(width, height) < MIN_DIMENSION_PX:
        return MetadataResult(
            path, False, [f"too small ({width}x{height})"], width, height, has_exif, filename_hint
        )

    aspect = max(width, height) / max(1, min(width, height))
    if aspect > MAX_ASPECT_RATIO:
        return MetadataResult(
            path,
            False,
            [f"extreme aspect ratio ({width}x{height} = {aspect:.1f}:1)"],
            width,
            height,
            has_exif,
            filename_hint,
        )

    reasons = []
    if filename_hint:
        reasons.append("filename hint matched")
    if has_exif:
        reasons.append("has EXIF")
    return MetadataResult(path, True, reasons, width, height, has_exif, filename_hint)


def run(dir_path: Path) -> list[MetadataResult]:
    return [
        check_metadata(p) for p in sorted(dir_path.iterdir()) if p.suffix.lower() in IMAGE_SUFFIXES
    ]


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "tests/needles/docs"
    start = time.perf_counter()
    results = run(target)
    elapsed = time.perf_counter() - start

    passed = sum(r.passed for r in results)
    per_image_ms = (elapsed / len(results) * 1000) if results else 0.0
    print(f"{passed}/{len(results)} passed metadata gate in {elapsed * 1000:.1f}ms ({per_image_ms:.2f}ms/image)")
    for r in results:
        status = "PASS" if r.passed else "DROP"
        print(f"  {status}  {r.path.name:<24} {r.width}x{r.height:<6} {'; '.join(r.reasons)}")
