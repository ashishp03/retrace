# Retrace — Build Plan

Step-by-step plan from empty repo to demo, mapped to the six-stage architecture in [`ARCHITECTURE.md`](./ARCHITECTURE.md). See [`CLAUDE.md`](./CLAUDE.md) for the full scope contract, data model, and rubric.

## Default resolutions for the open questions

`CLAUDE.md` lists 12 open questions that were meant to be settled before scaffolding. To make this plan concrete, each one is given a default below, chosen from what's actually available on this machine (`ollama` and `tesseract` are installed, `uv` is available for Python, `gh` is authenticated against `github.com/ashishp03/retrace`). **These are defaults, not decisions — override any of them and the plan updates accordingly.**

| # | Question | Default |
|---|---|---|
| 1 | Stage 4 serving | Local via **Ollama** (already installed) — pull a vision-capable Gemma checkpoint locally |
| 2 | Stage 5 Lambda deployment | Lambda Cloud on-demand GPU instance running a serving stack (Ollama or vLLM) exposing an HTTP endpoint for the larger Gemma checkpoint; provisioning is a blocking Phase 0 task |
| 3 | Nango / Respan accounts | Assume not yet created — provisioning + Gmail OAuth app setup is a blocking Phase 0 task |
| 4 | Respan project | Created from scratch, one routing config, calls tagged by `stage` + `doc_type` |
| 5 | Backend | Python + FastAPI, managed with `uv` |
| 6 | Frontend | Plain HTML/JS/CSS served as static files by FastAPI — no framework |
| 7 | Indexing execution | Background task (FastAPI `BackgroundTasks` or a simple thread) + a `/progress` endpoint the UI polls for a live counter |
| 8 | Repo structure | `ingest/`, `pipeline/`, `api/`, `web/`, `tests/` |
| 9 | Secrets | `.env` (gitignored) + `.env.example`; also now protected by a Claude Code hook (see below) |
| 10 | Real photo folder / Gmail inbox | Not yet available — build and validate against a small synthetic/sample doc set first, swap in the real folder path via `.env` when ready |
| 11 | Needle test | Automated — see the `needle-test` skill added alongside this plan |
| 12 | Demo flow / exact queries | Not locked — revisit in Phase 11 once real data is available |

---

## Phase 0 — Environment & keys (blocking)

**Goal:** every external dependency the pipeline needs is reachable before any pipeline code is written.

- [ ] Create/confirm Nango account, Gmail OAuth app, and a Nango connection for the target Gmail account
- [ ] Create/confirm Respan account and project; get an API key
- [ ] Create/confirm Lambda Cloud account; get an API key
- [ ] Confirm `ollama` can pull and run a vision-capable Gemma checkpoint locally (`ollama pull <model>`, run one test image through it)
- [ ] Scaffold `.env.example` with `NANGO_*`, `RESPAN_*`, `LAMBDA_*` placeholders; each person fills their own `.env`
- [ ] `gh` already authenticated against `ashishp03/retrace` — confirm push access works

**Exit criteria:** a `curl`/`ollama run` smoke test succeeds against local Ollama, and API keys for Nango, Respan, and Lambda are in `.env`.

---

## Phase 1 — Throughput spike (before full scaffolding)

`ARCHITECTURE.md` calls this out explicitly: measure throughput **before** writing the rest of the pipeline, because it decides whether the 800-image cap is realistic or needs to drop to 300.

- [ ] Grab ~50 sample images (mixed: real documents + junk photos)
- [ ] Write a throwaway script: metadata gate (stage 2) + OCR gate (stage 3) over all 50, timed
- [ ] Time one image end-to-end through stage 4 (local Ollama Gemma vision call + strict JSON parse)
- [ ] Compute: `(50-image stage 2-3 time) + (survivors × stage 4 time)` scaled to 800 images
- [ ] Decide: keep the 800-image cap, or drop to 300 — record the decision and the numbers in this file

**Exit criteria:** two real numbers (ms/image for stages 2-3, seconds/image for stage 4) and an explicit cap decision, not an assumption. This is exactly what the `pipeline-throughput` skill automates — run `/pipeline-throughput` once Phase 2 scaffolding exists so this becomes a repeatable check, not a one-off script.

---

## Phase 2 — Repo scaffolding

- [ ] `uv init`, create `pyproject.toml` with FastAPI, `pytesseract`, `pillow-heif`, `sqlite3` (stdlib), `python-dotenv`
- [ ] Create `ingest/`, `pipeline/`, `api/`, `web/`, `tests/`
- [ ] `.gitignore`: `.env`, staging/photo directories, `__pycache__/`, `.venv/`
- [ ] `.env.example` (from Phase 0) committed; real `.env` gitignored
- [ ] Empty SQLite schema file (`pipeline/schema.sql`) with the FTS5 table from `CLAUDE.md`'s data model

**Exit criteria:** `uv run python -c "import fastapi, pytesseract"` works; `git status` shows no secrets tracked.

---

## Phase 3 — Stage 1: Ingest

- [ ] Local photo folder walker: HEIC → JPEG via `pillow-heif`, copy into staging dir, tag `source: photos`
- [ ] Nango client: pull Gmail attachments (images + PDFs) into the same staging dir, tag `source: gmail`
- [ ] Both paths write into one staging directory with a manifest (file path, source, ingested_at)
- [ ] Cap enforcement: most recent 800 (or 300, per Phase 1 decision) images only

**Exit criteria:** running ingest against the sample folder + a test Gmail account populates the staging dir with correctly tagged files.

---

## Phase 4 — Stage 2: Metadata gate — **done** (`pipeline/metadata_gate.py`)

- [x] Filename heuristics (e.g. `IMG_`, `Screenshot`, `Photo`) as weak signals only
- [x] EXIF read (orientation, camera model — presence itself is a signal)
- [x] Aspect ratio / dimension filter (drop extreme wide/tall, drop tiny)
- [x] Loose by design — log what's demoted, don't hard-drop unless clearly junk

**Exit criteria — met:** 13/15 needles pass; `junk_panorama` (18.2:1 aspect) and `junk_tiny` (32x32) are the only drops, matching `manifest.json` exactly. 2.48ms/image over the 15 needles.

---

## Phase 5 — Stage 3: OCR gate — **done** (`pipeline/ocr_gate.py`)

- [x] `pytesseract` over survivors, count confident words
- [x] Threshold **lowered to 6** (from the stated default of 8) after real needle-doc behavior:
  `screenshot_03` is a genuine 7-word short text and was being wrongly dropped at 8
- [x] Persist `ocr_text` regardless of pass/fail — used as stage-4 hint and search fallback

**Exit criteria — met:** 12/15 needles pass, matching `manifest.json` exactly (all 4 doc types
extract; `junk_blank_photo`, `junk_panorama`, `junk_tiny` correctly drop). ~108ms/image —
within `ARCHITECTURE.md`'s ~100-300ms/image estimate.

**Finding worth knowing:** tesseract's automatic page-layout analysis can silently drop entire
text blocks on images that are mostly blank margin around a small amount of content (found via
`screenshot_03` — a full-page OCR call returned only the app-bar text, discarding both message
bubbles, until the image was cropped to its content bounding box first). Fixed by cropping to
content bbox + a small background-colored border before every OCR call — cheap since gate
images are small, and it's the more realistic case anyway (real phone screenshots/photos often
have large blank margins around the actual document).

---

## Phase 6 — Stage 4: Extract

- [ ] Local Ollama call: image + `ocr_text` hint → one strict JSON object per the `CLAUDE.md` schema
- [ ] Constrained/schema-forced decoding if the Ollama model supports it (structured outputs); otherwise strict parse + one retry + drop-on-second-failure
- [ ] Route the call through **Respan**, tagged `stage=extract`, `doc_type=<classified type once known>`
- [ ] Never let one bad response stall the batch — catch, log, continue

**Exit criteria:** all fifteen needle docs produce valid JSON matching the schema, with `null` (not guessed values) where fields are genuinely absent.

---

## Phase 7 — Stage 5: Cross-check

- [ ] Provision the Lambda-hosted larger Gemma checkpoint endpoint (from Phase 0)
- [ ] Route a sampled subset of stage-4 records to it via **Respan**, tagged `stage=crosscheck`, `doc_type=...`
- [ ] Field-by-field diff against stage-4 output → `agreement: high` or `agreement: flagged`
- [ ] Flagged records visibly marked for the human review queue in the data model

**Exit criteria:** at least one deliberately-planted needle doc with an ambiguous field produces a `flagged` result, proving disagreement actually routes to review — not just the happy path.

---

## Phase 8 — Stage 6: Store & search

- [ ] SQLite table + FTS5 virtual table over extracted fields + `ocr_text` (schema from `CLAUDE.md`)
- [ ] Insert path from stages 4-6 (including `flagged` records — they're still searchable, just marked)
- [ ] No vector DB, no embeddings — FTS5 only

**Exit criteria:** a manual FTS5 query against a few inserted needle docs returns the right rows.

---

## Phase 9 — API + Web UI

- [ ] FastAPI: `/search?q=`, `/progress` (for the live indexing counter), static file serving for `web/`
- [ ] Single HTML page: search box, results list rendering `title`, `date`, `amount`/`entity` as available, `agreement` badge
- [ ] Live progress counter wired to `/progress` during a run (background task + polling, per default #7)
- [ ] Read-only — no edit/export UI

**Exit criteria:** searching for a needle doc's merchant name or an OCR fragment returns it in the UI.

---

## Phase 10 — Needle test validation

- [ ] Confirm all fifteen needle docs are planted in the sample folder
- [ ] Run the `needle-test` skill end-to-end; every needle doc should reach the expected stage and produce the expected fields
- [ ] Re-run after every pipeline change from here on

**Exit criteria:** `needle-test` reports 15/15 reaching their expected outcome (extracted, or intentionally dropped, per each needle's design).

---

## Phase 11 — Demo prep

- [ ] Point ingest at the real photo folder / real Gmail inbox (default #10, once available)
- [ ] Pre-index fully — the demo must not depend on live model calls except the Nango sync and the Respan-routed Lambda call
- [ ] Turn off wifi locally and confirm search still works end-to-end
- [ ] Lock in the 3 demo search queries (default #12) and rehearse the 3-minute walkthrough
- [ ] Rehearse the commercial-viability Q&A answer (who buys it, why local-only is the sellable feature, what's next)
- [ ] Spot-check that every Respan call in the demo path is tagged by stage/doc_type (dashboard should read cleanly) — this is exactly what the `respan-call-auditor` subagent checks

**Exit criteria:** full demo run, network off except the two allowed calls, completes without errors, on the real data.

---

## Ongoing, not a phase

- Re-run `needle-test` after every pipeline change (Phase 10 skill)
- Keep Respan calls tagged — checked by the `respan-call-auditor` subagent
- Keep stage-4/5 JSON output honest (`null` over guesses) — checked by the `schema-guard` subagent
- If tempted to add a queue, a second database, or a config system: stop and ask first — not in scope for a 5.5-hour build
