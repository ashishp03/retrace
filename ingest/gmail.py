"""Stage 1 (Gmail half) — pull image attachments out of Gmail via Nango, stage them, then run
them through the existing pipeline (stages 2-5) and store them (stage 6), tagged `source: gmail`.

Images only, by design (current decision — see CHECKPOINT2.md/summary.md): PDFs and DOCX
attachments are skipped. Not a limitation of Nango or Gmail, a scope call — everything else in the
pipeline (metadata gate, OCR gate, the vision extractor/verifier) already operates on images only,
and adding PDF/DOCX parsing is out of scope for now.

Incremental: a small `.synced_message_ids.json` file in the staging dir tracks which Gmail message
IDs have already been processed, so re-running only fetches genuinely new mail instead of
re-downloading and re-extracting everything every sync.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
from crosscheck import crosscheck  # noqa: E402
from extract import extract  # noqa: E402
from metadata_gate import check_metadata  # noqa: E402
from ocr_gate import check_ocr  # noqa: E402
from store import get_conn, insert_document  # noqa: E402

NANGO_SECRET_KEY = os.environ.get("NANGO_SECRET_KEY")
NANGO_CONNECTION_ID = os.environ.get("NANGO_CONNECTION_ID")
NANGO_INTEGRATION_ID = os.environ.get("NANGO_INTEGRATION_ID", "google-mail")
NANGO_PROXY_BASE = "https://api.nango.dev/proxy"

GMAIL_STAGING_DIR = Path(os.environ.get("GMAIL_STAGING_DIR", "./ingest/staging/gmail"))
DB_PATH = os.environ.get("DB_PATH", "./api/retrace.db")
SEEN_FILE = GMAIL_STAGING_DIR / ".synced_message_ids.json"

IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NANGO_SECRET_KEY}",
        "Connection-Id": NANGO_CONNECTION_ID,
        "Provider-Config-Key": NANGO_INTEGRATION_ID,
    }


def _list_message_ids(max_results: int = 50) -> list[str]:
    resp = requests.get(
        f"{NANGO_PROXY_BASE}/gmail/v1/users/me/messages",
        params={"maxResults": max_results},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("messages", [])]


def _get_message(message_id: str) -> dict:
    resp = requests.get(
        f"{NANGO_PROXY_BASE}/gmail/v1/users/me/messages/{message_id}",
        params={"format": "full"},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_attachment_bytes(message_id: str, attachment_id: str) -> bytes:
    resp = requests.get(
        f"{NANGO_PROXY_BASE}/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _image_parts(payload: dict) -> list[dict]:
    found = []

    def walk(part: dict) -> None:
        if part.get("filename") and part.get("mimeType") in IMAGE_MIME_TYPES:
            found.append(part)
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    return found


def _load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def fetch_new_attachments() -> list[Path]:
    """Pull any Gmail message not seen before, save its image attachments to the staging dir.
    Returns the list of newly staged image paths (empty if nothing new)."""
    GMAIL_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    seen = _load_seen()
    staged: list[Path] = []

    for message_id in _list_message_ids():
        if message_id in seen:
            continue
        message = _get_message(message_id)
        for part in _image_parts(message["payload"]):
            attachment_id = part["body"]["attachmentId"]
            content = _get_attachment_bytes(message_id, attachment_id)
            ext = IMAGE_EXT.get(part["mimeType"], Path(part["filename"]).suffix or ".png")
            out_path = GMAIL_STAGING_DIR / f"{message_id}_{Path(part['filename']).stem}{ext}"
            out_path.write_bytes(content)
            staged.append(out_path)
        seen.add(message_id)

    _save_seen(seen)
    return staged


def index_staged_images(paths: list[Path]) -> list[dict]:
    """Run newly staged Gmail images through stages 2-6, tagged source=gmail. Appends to the
    existing DB rather than wiping it (unlike pipeline/store.py's __main__, which is for
    from-scratch test runs)."""
    conn = get_conn(DB_PATH)
    results = []
    for path in paths:
        meta = check_metadata(path)
        if not meta.passed:
            results.append({"file": path.name, "outcome": "dropped_at_metadata"})
            continue
        ocr = check_ocr(path)
        if not ocr.passed:
            results.append({"file": path.name, "outcome": "dropped_at_ocr"})
            continue
        stage4 = extract(path, ocr.ocr_text)
        if not stage4.ok:
            results.append({"file": path.name, "outcome": "extract_failed", "error": stage4.error})
            continue
        cc = crosscheck(path, stage4.fields, ocr.ocr_text)
        doc_id = insert_document(
            conn, fields=stage4.fields, source="gmail", file_path=str(path),
            ocr_text=ocr.ocr_text, agreement=cc.agreement,
        )
        results.append({"file": path.name, "outcome": "extracted", "id": doc_id,
                         "agreement": cc.agreement, "fields": stage4.fields})
    return results


def sync_gmail() -> dict:
    start = time.perf_counter()
    staged = fetch_new_attachments()
    results = index_staged_images(staged)
    return {
        "elapsed_s": time.perf_counter() - start,
        "new_messages_checked": len(staged),
        "indexed": sum(1 for r in results if r["outcome"] == "extracted"),
        "results": results,
    }


if __name__ == "__main__":
    summary = sync_gmail()
    print(json.dumps(summary, indent=2))
