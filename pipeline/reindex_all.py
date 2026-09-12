"""Reindex every test corpus (needles + sample_batch) into one fresh DB, so the demo has
enough variety for real questions (multiple receipts, multiple cards, multiple forms) instead of
just whichever single directory was last run through store.py.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from crosscheck import crosscheck
from extract import extract
from metadata_gate import run as run_metadata
from ocr_gate import check_ocr
from store import get_conn, insert_document

TARGETS = [
    (Path(__file__).parent.parent / "tests/needles/docs", "photos"),
    (Path(__file__).parent.parent / "tests/sample_batch/docs", "photos"),
]


def main() -> None:
    db_path = str(Path(__file__).parent.parent / "api/retrace.db")
    Path(db_path).unlink(missing_ok=True)
    conn = get_conn(db_path)

    start = time.perf_counter()
    inserted = 0
    for target, source in TARGETS:
        if not target.exists():
            print(f"  SKIP (missing) {target}")
            continue
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
            insert_document(
                conn, fields=stage4.fields, source=source, file_path=str(m.path),
                ocr_text=ocr.ocr_text, agreement=cc.agreement,
            )
            inserted += 1
            print(f"  STORED  {m.path.name:<24} agreement={cc.agreement}")
    elapsed = time.perf_counter() - start
    print(f"\n{inserted} documents stored in {elapsed:.1f}s -> {db_path}")


if __name__ == "__main__":
    main()
