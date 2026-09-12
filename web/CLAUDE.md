# web/ — Search Page

> Local goals and scope for this folder. Root [`../CLAUDE.md`](../CLAUDE.md) is the source of
> truth for the scope contract and demo constraints — read it first.

**Role:** One local web page, one search box. No mobile app, no accounts, no editing.

- Talks to `api/` for full-text search over extracted fields + OCR text (SQLite FTS5 underneath —
  never build a client-side index here).
- Default assumption per root `CLAUDE.md`'s open questions: plain HTML/JS/CSS served by the
  backend, not a framework — confirm before adding one.
- If indexing runs as a background worker, this is where a live progress counter would poll the
  `api/` progress endpoint during the demo.

**Not yet built.** Blocked on open questions in the root `CLAUDE.md`: frontend approach
confirmation, and which exact search queries the demo will run (worth locking in so the UI is
built around them).

**Constraints:**
- Read-only: no forms that edit or export records.
- Network-off demo: must render and query fully offline against the pre-indexed local `api/`.
