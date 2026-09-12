"""Stage 4 — Extract. Local Ollama vision call (gemma4:e4b) over an image + the stage-3 OCR
hint, one strict JSON object per the CLAUDE.md data model. Retries once on parse failure, drops
the record on a second failure — one bad response must never stall the batch.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "gemma4:e4b")

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": ["string", "null"], "enum": ["receipt", "card", "form", "screenshot_text", None]},
        "title": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "amount": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "entity": {"type": ["string", "null"]},
        "identifiers": {"type": "array", "items": {"type": "string"}},
        "key_values": {"type": "object"},
        "summary": {"type": ["string", "null"]},
    },
    "required": ["doc_type", "title", "date", "amount", "currency", "entity", "identifiers", "key_values", "summary"],
}

PROMPT_TEMPLATE = """You are extracting structured data from a single document image (a receipt, \
card/ID, form/letter, or screenshot of text). OCR text extracted from the image is given below as \
a hint — it may be incomplete or noisy, trust the image itself first.

Return ONLY a JSON object with exactly these keys:
- doc_type: one of "receipt", "card", "form", "screenshot_text"
- title: short human title, e.g. "Blue Bottle Coffee — 14 Aug 2026"
- date: ISO date (YYYY-MM-DD) if present, else null. NEVER guess a date.
- amount: total amount as a number, receipts only, else null. NEVER guess.
- currency: e.g. "USD", else null
- entity: merchant / issuer / sender name, else null
- identifiers: array of card/policy/account numbers found, else []
- key_values: object of any other notable field: value pairs found (e.g. {{"expires": "2029-03"}}), else {{}}
- summary: one sentence describing what this document is

Rule: return null (or [] / {{}}) rather than guessing. A confidently wrong value is worse than a blank one.

OCR text hint:
{ocr_text}
"""


@dataclass
class ExtractResult:
    path: Path
    ok: bool
    fields: dict | None
    error: str | None
    elapsed_s: float


def _call_ollama(image_path: Path, ocr_text: str) -> dict:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": OLLAMA_VISION_MODEL,
            "prompt": PROMPT_TEMPLATE.format(ocr_text=ocr_text[:2000] or "(none)"),
            "images": [image_b64],
            "stream": False,
            "format": RESPONSE_SCHEMA,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["response"])


def extract(path: Path, ocr_text: str) -> ExtractResult:
    start = time.perf_counter()
    last_error = None
    for attempt in range(2):
        try:
            fields = _call_ollama(path, ocr_text)
            return ExtractResult(path, True, fields, None, time.perf_counter() - start)
        except Exception as e:
            last_error = str(e)
    return ExtractResult(path, False, None, last_error, time.perf_counter() - start)


if __name__ == "__main__":
    from metadata_gate import run as run_metadata
    from ocr_gate import check_ocr

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "tests/needles/docs"
    meta_results = [r for r in run_metadata(target) if r.passed]

    start = time.perf_counter()
    extracted = 0
    records = []
    for m in meta_results:
        ocr = check_ocr(m.path)
        if not ocr.passed:
            print(f"  DROP(ocr)  {m.path.name}")
            records.append({"file": m.path.name, "outcome": "dropped_at_ocr"})
            continue
        result = extract(m.path, ocr.ocr_text)
        if result.ok:
            extracted += 1
            print(f"  OK  {m.path.name:<24} {result.elapsed_s:.2f}s  {json.dumps(result.fields)}")
            records.append({"file": m.path.name, "outcome": "extracted",
                             "elapsed_s": result.elapsed_s, "fields": result.fields})
        else:
            print(f"  FAIL  {m.path.name:<24} {result.error}")
            records.append({"file": m.path.name, "outcome": "failed", "error": result.error})
    elapsed = time.perf_counter() - start
    print(f"\n{extracted}/{len(meta_results)} extracted in {elapsed:.1f}s ({elapsed / max(1, len(meta_results)):.2f}s/image)")

    out_dir = Path(__file__).parent.parent / "outputs/extract"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "target": str(target),
        "elapsed_s": elapsed,
        "extracted": extracted,
        "total_after_metadata_gate": len(meta_results),
        "s_per_image": elapsed / max(1, len(meta_results)),
        "records": records,
    }
    (out_dir / "results.json").write_text(json.dumps(out, indent=2))
