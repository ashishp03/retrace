# api/ — Stage 6 + Serving

> Local goals and scope for this folder. Root [`../CLAUDE.md`](../CLAUDE.md) is the source of
> truth for the data model, scope contract, and constraints — read it first.

**Role:** Store extracted records and serve the search page. One table, SQLite + FTS5 virtual
table over extracted fields + OCR text. No vector DB, no embeddings, no semantic search.

- Serves `web/`'s single search page: full-text query in, matching records out.
- If indexing runs as a background worker (open question in root `CLAUDE.md`), this is where the
  progress endpoint the UI polls would live.
- Read-only from the API's perspective — no editing or exporting records (root scope contract).

**Not yet built.** Blocked on open questions in the root `CLAUDE.md`: backend
language/framework, and whether indexing is triggered on demand or runs as a background worker
with a polled progress endpoint.

**Constraints:**
- No auth, no accounts, no multi-user.
- Network-off demo: this layer must work entirely offline — it only ever reads/writes the local
  SQLite file, no external calls.
