"""Stage 6 — Store & search. SQLite + FTS5 over extracted fields + OCR text. No vector DB.

Also runs the full stage 1(local folder)->6 chain over a directory, for demo/testing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "./api/retrace.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def insert_document(conn: sqlite3.Connection, *, fields: dict, source: str, file_path: str,
                     ocr_text: str, agreement: str | None) -> int:
    cur = conn.execute(
        """INSERT INTO documents
           (doc_type, title, date, amount, currency, entity, identifiers, key_values, summary,
            source, file_path, taken_at, ocr_text, agreement)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fields.get("doc_type"), fields.get("title"), fields.get("date"), fields.get("amount"),
            fields.get("currency"), fields.get("entity"), json.dumps(fields.get("identifiers") or []),
            json.dumps(fields.get("key_values") or {}), fields.get("summary"),
            source, file_path, None, ocr_text, agreement,
        ),
    )
    conn.commit()
    return cur.lastrowid


def search(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """SELECT documents.* FROM documents_fts
           JOIN documents ON documents.id = documents_fts.rowid
           WHERE documents_fts MATCH ? ORDER BY rank""",
        (query,),
    ).fetchall()


if __name__ == "__main__":
    from crosscheck import crosscheck
    from extract import extract
    from metadata_gate import run as run_metadata
    from ocr_gate import check_ocr

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "tests/needles/docs"
    db_path = os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "api/retrace.db"))
    Path(db_path).unlink(missing_ok=True)
    conn = get_conn(db_path)

    start = time.perf_counter()
    inserted = 0
    stored_records = []
    for m in run_metadata(target):
        if not m.passed:
            continue
        ocr = check_ocr(m.path)
        if not ocr.passed:
            continue
        stage4 = extract(m.path, ocr.ocr_text)
        if not stage4.ok:
            print(f"  FAIL(extract)  {m.path.name}  {stage4.error}")
            continue
        cc = crosscheck(m.path, stage4.fields, ocr.ocr_text)
        doc_id = insert_document(
            conn, fields=stage4.fields, source="photos", file_path=str(m.path),
            ocr_text=ocr.ocr_text, agreement=cc.agreement,
        )
        inserted += 1
        print(f"  STORED  {m.path.name:<24} agreement={cc.agreement}")
        stored_records.append({
            "id": doc_id, "file": m.path.name, "agreement": cc.agreement,
            "diffs": cc.diffs,
            "verifier_fields": cc.verifier_fields,
            "arbiter": None if cc.arbiter is None else {
                "agreement": cc.arbiter.agreement, "resolution": cc.arbiter.resolution,
                "reasoning": cc.arbiter.reasoning,
            },
            "fields": stage4.fields,
        })
    elapsed = time.perf_counter() - start
    print(f"\n{inserted} documents stored in {elapsed:.1f}s -> {db_path}")

    search_output = {}
    for q in ("coffee", "DMV", "policy"):
        rows = search(conn, q)
        print(f"\nsearch '{q}' -> {len(rows)} result(s)")
        search_output[q] = []
        for r in rows:
            print(f"    {r['title']}  ({r['doc_type']}, agreement={r['agreement']})")
            search_output[q].append({
                "title": r["title"], "doc_type": r["doc_type"], "agreement": r["agreement"],
                "entity": r["entity"], "date": r["date"], "amount": r["amount"],
            })

    import json

    out_dir = Path(__file__).parent.parent / "outputs/store"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "target": str(target),
        "db_path": db_path,
        "elapsed_s": elapsed,
        "inserted": inserted,
        "documents": stored_records,
        "sample_searches": search_output,
    }
    (out_dir / "results.json").write_text(json.dumps(out, indent=2))
