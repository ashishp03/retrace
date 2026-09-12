# Retrace — Status Summary

Rolling status doc: what's set up, what's done, what's next, per branch. Not evergreen — update or
delete stale sections as the build moves; `CLAUDE.md` / `plan.md` are the stable references, this
file is the "where are we right now."

## Branches

### `main`
Trunk — environment/toolchain baseline only, no pipeline code.
- Commit `32ba373` "Updates": `pyproject.toml` + `uv.lock` (uv-managed deps: fastapi, uvicorn,
  pytesseract, pillow, pillow-heif, python-dotenv; dev group: pytest), `.python-version` (3.12),
  `.gitignore`, `.env.example`, README setup instructions.
- Also has (from earlier commits, before any branch split): root `CLAUDE.md`, `ARCHITECTURE.md`,
  `plan.md`, per-folder `CLAUDE.md` in `ingest/` `pipeline/` `api/` `web/`, `.claude/` hooks
  (env/secrets guards), `.claude/agents/` (`schema-guard`, `respan-call-auditor`), `.claude/skills/`
  (`needle-test`, `pipeline-throughput`).
- No pipeline/product code lives here yet — that's `build-pipeline`'s job until it merges back.

### `build-pipeline` (current branch)
Everything from `main`, plus the six-stage pipeline build in progress.
- Commit `704c47e` "Needle Tests": `pipeline/schema.sql` (SQLite + FTS5 schema matching the
  `CLAUDE.md` data model), `tests/needles/generate_needles.py` (synthetic needle-doc generator),
  `tests/needles/manifest.json` (15 needles: 3 receipt / 3 card / 3 form / 3 screenshot_text,
  extracted; 2 dropped_at_metadata + 1 dropped_at_ocr, negative).
- **Not committed, regenerated on demand:** the 15 actual `.png` files under `tests/needles/docs/`
  — gitignored on purpose (`*.png`), since the generator + manifest are the source of truth and the
  images aren't portable build artifacts (hardcoded macOS font paths). Run
  `uv run python tests/needles/generate_needles.py` after a fresh clone — documented in the README.
- Uncommitted right now:
  - `.gitignore` cleanup (dropped a dead `tests/fixtures/` rule) + README addition documenting the
    needle-generation step
  - `pipeline/metadata_gate.py` (Stage 2) — 13/15 needles pass, matches `manifest.json` exactly
  - `pipeline/ocr_gate.py` (Stage 3) — 12/15 needles pass, matches `manifest.json` exactly;
    includes a content-bounding-box crop fix for a real tesseract layout-analysis failure found
    via needle testing, and the OCR word threshold is now 6 (was 8) per real needle behavior
  - `summary.md` (this file)
  - All waiting on you to review and commit.

## Verified working
- Fresh-clone `uv sync --locked` reproduces the pinned env exactly (Python 3.12.13, 22 packages);
  all deps import cleanly.
- `tesseract 5.5.0` and `ollama` are installed locally; `ollama list` currently shows only
  `qwen2.5-coder:7b` — the vision-capable Gemma checkpoint is still downloading (Phase 0, #1).
- 15 needle docs render as legible synthetic documents (spot-checked `receipt_01.png`).

## Plan.md phase status

| Phase | Status |
|---|---|
| 0 — Env & keys | Partial: fake Gmail account created; vision model download in progress. Nango/Respan/Lambda accounts+keys not yet confirmed. |
| 1 — Throughput spike | Not run — blocked on stage 2/3 code existing (about to start) and, for stage 4, the model download. |
| 2 — Repo scaffolding | **Done** (on `main`, inherited by `build-pipeline`). |
| 3 — Stage 1 Ingest | Not built — blocked on Phase 0 keys (Nango) for the Gmail half; local photo-folder half is unblocked. |
| **4 — Stage 2 Metadata gate** | **Done.** 13/15 needles pass, matches manifest exactly. 2.48ms/image. |
| **5 — Stage 3 OCR gate** | **Done.** 12/15 needles pass, matches manifest exactly. ~108ms/image. Threshold tuned 8→6 from real needle behavior; found + fixed a real tesseract layout bug (see `plan.md` Phase 5). |
| 6 — Stage 4 Extract | Blocked on the vision model download. |
| 7 — Stage 5 Cross-check | Blocked on Lambda/Respan provisioning. |
| 8 — Stage 6 Store & search | Schema written; no insert/query code yet. |
| 9 — API + Web UI | Not started. |
| 10 — Needle test validation | Stages 2–3 individually validated against all 15 needles (see above). Full `needle-test` skill run still needs stages 4–6 to exist. |
| 11 — Demo prep | Not started. |

## Right now

Stage 2 + Stage 3 are implemented and needle-validated. The `pipeline-throughput` skill (which
would give the formal 800-vs-300 image cap decision) explicitly refuses to run until stage 4 code
also exists — so that decision stays blocked on the vision model finishing its download, by design.

**Next, still without the model:** Stage 1 ingest's local-photo-folder half (HEIC→JPEG walker,
tagging `source: photos`) — the Nango/Gmail half needs Phase 0 keys, but the local half doesn't.
