"""Stage 5 — Cross-check. Three distinct agent roles, not three copies of the same job:

  1. Stage 4 (elsewhere, extract.py) already produced an extraction: local `gemma4:e4b`.
  2. **Verifier** (`_call_lambda_gemma`) — a second, larger, independent Gemma checkpoint
     (`gemma3:27b`) hosted on a **Lambda** GPU instance, reached over an SSH tunnel to its Ollama
     server. It re-reads the same image blind to stage 4's answer. This is the literal "second,
     larger Gemma checkpoint hosted on Lambda" CLAUDE.md's stage 5 spec calls for.
  3. **Arbiter** (`_call_respan_arbiter`) — only dispatched when the extractor and verifier
     actually disagree on a field. It doesn't re-extract anything from the image; it's handed
     both candidate values + the OCR text and has to reason about which is more likely correct,
     or decide the conflict needs a human. Routed through **Respan** (`anthropic/claude-haiku-4-5`,
     text-only — no image needed for this job), tagged `stage=crosscheck`, `doc_type`, and
     `role=arbiter` so its calls are distinguishable from a plain extraction call on the Respan
     dashboard.

Most documents have the extractor and verifier agree outright (two models reading a clear
receipt total should usually match) — the arbiter is a conditional escalation, not a third
parallel vote. That's the point: coordination should look like "call in a specialist when there's
an actual conflict to resolve," not "run everything three times and diff."
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

RESPAN_API_KEY = os.environ.get("RESPAN_API_KEY")
RESPAN_BASE_URL = os.environ.get("RESPAN_BASE_URL", "https://api.respan.ai/api/")
RESPAN_ARBITER_MODEL = os.environ.get("RESPAN_CROSSCHECK_MODEL", "anthropic/claude-haiku-4-5")

LAMBDA_ENDPOINT_URL = os.environ.get("LAMBDA_ENDPOINT_URL", "http://localhost:11435")
LAMBDA_VISION_MODEL = os.environ.get("LAMBDA_VISION_MODEL", "gemma3:27b")

DIFF_FIELDS = ("doc_type", "date", "amount", "entity")

VERIFIER_PROMPT = """Extract structured data from this document image. Return ONLY a JSON object \
with exactly these keys: doc_type (one of "receipt", "card", "form", "screenshot_text"), title, \
date (ISO YYYY-MM-DD or null), amount (number or null, receipts only), currency, entity, \
identifiers (array of strings), key_values (object), summary (one sentence). Return null/[]/{{}} \
rather than guessing.
"""

ARBITER_PROMPT = """Two independent vision models extracted fields from the same document image \
and disagree on some of them. You do NOT have the image — decide using the values below plus the \
OCR text hint, the same way a human reviewer would triage a conflict.

Extractor A (local Gemma, smaller model): {a_fields}
Extractor B (Lambda-hosted Gemma, larger model): {b_fields}
Disputed fields: {diffs}
OCR text hint: {ocr_text}

Return ONLY a JSON object:
{{
  "agreement": "resolved" or "flagged",   // "resolved" if you can confidently pick a correct value
                                            // for every disputed field from the OCR hint; "flagged"
                                            // if a human should look at it
  "resolution": {{"<field>": <value>, ...}},  // your best value for each disputed field, or {{}} if flagged
  "reasoning": "one sentence explaining the decision"
}}
"""


@dataclass
class ArbiterDecision:
    agreement: str  # "resolved" | "flagged"
    resolution: dict
    reasoning: str


@dataclass
class CrossCheckResult:
    path: Path
    agreement: str  # "high" | "flagged"
    verifier_ok: bool
    verifier_fields: dict | None
    verifier_error: str | None
    diffs: list[str] = field(default_factory=list)
    arbiter: ArbiterDecision | None = None


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def _diff(stage4_fields: dict, verifier_fields: dict) -> list[str]:
    return [
        f for f in DIFF_FIELDS
        if str(stage4_fields.get(f)).strip().lower() != str(verifier_fields.get(f)).strip().lower()
    ]


def _call_lambda_gemma(image_path: Path) -> dict:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = requests.post(
        f"{LAMBDA_ENDPOINT_URL}/api/generate",
        json={
            "model": LAMBDA_VISION_MODEL,
            "prompt": VERIFIER_PROMPT,
            "images": [image_b64],
            "stream": False,
            "format": "json",
        },
        timeout=120,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["response"])


def _verify(image_path: Path) -> tuple[bool, dict | None, str | None]:
    last_error = None
    for attempt in range(2):
        try:
            return True, _call_lambda_gemma(image_path), None
        except Exception as e:
            last_error = str(e)
    return False, None, last_error


def _call_respan_arbiter(a_fields: dict, b_fields: dict, diffs: list[str], ocr_text: str,
                          doc_type_hint: str | None) -> ArbiterDecision:
    client = OpenAI(base_url=RESPAN_BASE_URL, api_key=RESPAN_API_KEY)
    prompt = ARBITER_PROMPT.format(
        a_fields=json.dumps(a_fields), b_fields=json.dumps(b_fields),
        diffs=diffs, ocr_text=(ocr_text or "")[:1000],
    )
    resp = client.chat.completions.create(
        model=RESPAN_ARBITER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"metadata": {"stage": "crosscheck", "role": "arbiter", "doc_type": doc_type_hint or "unknown"}},
    )
    decision = _parse_json(resp.choices[0].message.content)
    return ArbiterDecision(
        agreement=decision.get("agreement", "flagged"),
        resolution=decision.get("resolution", {}),
        reasoning=decision.get("reasoning", ""),
    )


def crosscheck(path: Path, stage4_fields: dict, ocr_text: str = "") -> CrossCheckResult:
    verifier_ok, verifier_fields, verifier_error = _verify(path)

    if not verifier_ok:
        # Verifier didn't respond -> nothing to corroborate stage 4 with. Flag for review rather
        # than silently trusting a single model.
        return CrossCheckResult(path, "flagged", False, None, verifier_error)

    diffs = _diff(stage4_fields, verifier_fields)
    if not diffs:
        return CrossCheckResult(path, "high", True, verifier_fields, None, diffs=[])

    # Extractor and verifier actually disagree -> dispatch the arbiter. This is the conditional
    # escalation: most documents never reach this call.
    try:
        decision = _call_respan_arbiter(stage4_fields, verifier_fields, diffs, ocr_text,
                                         stage4_fields.get("doc_type"))
    except Exception as e:
        decision = ArbiterDecision(agreement="flagged", resolution={}, reasoning=f"arbiter call failed: {e}")

    final_agreement = "high" if decision.agreement == "resolved" else "flagged"
    return CrossCheckResult(path, final_agreement, True, verifier_fields, None, diffs, decision)


if __name__ == "__main__":
    from extract import extract
    from metadata_gate import run as run_metadata
    from ocr_gate import check_ocr

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "tests/needles/docs"
    meta_results = [r for r in run_metadata(target) if r.passed]

    start = time.perf_counter()
    records = []
    arbiter_calls = 0
    for m in meta_results:
        ocr = check_ocr(m.path)
        if not ocr.passed:
            continue
        stage4 = extract(m.path, ocr.ocr_text)
        if not stage4.ok:
            print(f"  SKIP(extract failed)  {m.path.name}  {stage4.error}")
            records.append({"file": m.path.name, "outcome": "extract_failed", "error": stage4.error})
            continue
        cc = crosscheck(m.path, stage4.fields, ocr.ocr_text)
        if cc.arbiter is not None:
            arbiter_calls += 1
            tag = "RESOLVED" if cc.agreement == "high" else "FLAGGED "
            print(f"  {tag} {m.path.name:<24} diffs={cc.diffs}  arbiter: {cc.arbiter.reasoning}")
        else:
            tag = "HIGH    " if cc.agreement == "high" else "FLAGGED "
            note = cc.verifier_error if not cc.verifier_ok else "-"
            print(f"  {tag} {m.path.name:<24} diffs={cc.diffs or '-'}  {note if not cc.verifier_ok else ''}")
        records.append({
            "file": m.path.name,
            "agreement": cc.agreement,
            "stage4_fields": stage4.fields,
            "verifier_ok": cc.verifier_ok,
            "verifier_fields": cc.verifier_fields,
            "verifier_error": cc.verifier_error,
            "diffs": cc.diffs,
            "arbiter": None if cc.arbiter is None else {
                "agreement": cc.arbiter.agreement,
                "resolution": cc.arbiter.resolution,
                "reasoning": cc.arbiter.reasoning,
            },
        })
    elapsed = time.perf_counter() - start
    print(f"\ndone in {elapsed:.1f}s ({arbiter_calls}/{len(records)} docs escalated to the arbiter)")

    out_dir = Path(__file__).parent.parent / "outputs/crosscheck"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "target": str(target),
        "elapsed_s": elapsed,
        "verifier_model": LAMBDA_VISION_MODEL,
        "arbiter_model": RESPAN_ARBITER_MODEL,
        "high": sum(1 for r in records if r.get("agreement") == "high"),
        "flagged_count": sum(1 for r in records if r.get("agreement") == "flagged"),
        "arbiter_dispatched": arbiter_calls,
        "records": records,
    }
    (out_dir / "results.json").write_text(json.dumps(out, indent=2))
