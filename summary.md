# Retrace — Handover / Checkpoint

**Read this first if you're picking up this work on a different machine.** This is the current
state of the `build-pipeline` branch as of this checkpoint — what's built, what's verified, what's
uncommitted, and exactly what to do next. `CLAUDE.md` is the stable scope/architecture reference;
`plan.md` is the phase-by-phase build plan; this file is "where the last session actually left off."

## Get set up on this machine

1. `git checkout build-pipeline` (this is where all pipeline work lives — `main` is toolchain-only)
2. `uv sync` — installs the exact pinned deps + Python 3.12 (see README for full setup steps)
3. `uv run python tests/needles/generate_needles.py` — regenerates the 15 synthetic test docs.
   **These are gitignored on purpose** (`*.png` in `.gitignore`) — they're generated, not
   committed, because the generator hardcodes macOS font paths and isn't portable. Run this once
   after cloning or you'll have `tests/needles/manifest.json` pointing at files that don't exist.
4. Confirm Ollama has the vision model: `ollama list` should show `gemma4:e4b` (9.6GB). If it's not
   there, `ollama pull gemma4:e4b` — this is the model Stage 4 (extract) calls. Confirmed
   capabilities via `ollama show gemma4:e4b`: vision, tools, completion.
5. No `.env` exists yet on this machine — copy `.env.example` → `.env` if you have real Nango/
   Respan/Lambda keys. **Nobody has these keys yet** (see Blockers below), so most of the pipeline
   so far runs with zero keys.

## Branch state

- `main`: toolchain only (`pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`,
  `.env.example`, README setup instructions) + the original scope docs (`CLAUDE.md`,
  `ARCHITECTURE.md`, `plan.md`, per-folder `CLAUDE.md`s, `.claude/` hooks/agents/skills). No
  pipeline code. Don't merge `build-pipeline` into `main` until the pipeline reaches a coherent,
  demoable slice (discussed and deliberately deferred — see git log commit messages for the
  reasoning if needed).
- `build-pipeline` (**work here**): everything from `main`, plus the pipeline build.

### Committed on `build-pipeline` (HEAD = `8b7013b "Metdata gate and ocr gate initial tests"`)
- `pipeline/schema.sql` — SQLite + FTS5 schema matching the `CLAUDE.md` data model
- `tests/needles/generate_needles.py` + `tests/needles/manifest.json` — 15 synthetic needle docs
  (3 receipt / 3 card / 3 form / 3 screenshot_text — all expected `extracted`; 2
  `dropped_at_metadata` + 1 `dropped_at_ocr` — negative needles proving the gates actually gate)
- `pipeline/metadata_gate.py` (**Stage 2 — done**) — 13/15 needles pass, exactly matching
  `manifest.json`. 2.48ms/image.
- `pipeline/ocr_gate.py` (**Stage 3 — done**) — 12/15 needles pass, exactly matching
  `manifest.json`. ~108ms/image. See "Gotchas" below for two non-obvious things in this file.
- `plan.md` Phases 4 & 5 marked done with real numbers; `.gitignore`/README fixes.

### Uncommitted right now on this machine (not yet reviewed/committed)
- `pyproject.toml` + `uv.lock`: added `requests` (for calling Ollama's REST API) and `openai`
  (the client library Respan's API is compatible with — see `examples/respan-call.py`)
- `examples/respan-call.py` (untracked, new): a reference snippet showing how Respan is actually
  called — **it's the OpenAI client pointed at a different `base_url`**:
  ```python
  from openai import OpenAI
  client = OpenAI(base_url="https://api.respan.ai/api/", api_key="YOUR_RESPAN_API_KEY")
  response = client.chat.completions.create(model="gpt-5.4", messages=[...])
  ```
  This is what Stage 4/5's eventual Respan routing should be built against once a real Respan key
  exists. It is NOT wired into any pipeline code yet — it's just the reference for the interface
  shape.
- **`pipeline/extract.py` (Stage 4) does NOT exist yet** — this is the immediate next step, see
  below. Nothing has been built for it beyond confirming the model works and deciding the
  approach.

## Verified working (facts, not assumptions)
- Fresh-clone `uv sync --locked` reproduces the pinned env exactly (Python 3.12.13, 22+ packages).
- `tesseract 5.5.0` installed; Ollama running locally with `gemma4:e4b` (vision+tools+completion
  capable, confirmed via `ollama show`) and `qwen2.5-coder:7b` also present.
- Stage 2 + Stage 3 both independently validated against all 15 needles, exact match to
  `manifest.json` expectations (see numbers above).
- **Not yet independently re-verified this session:** an actual end-to-end vision call to
  `gemma4:e4b` against a needle image. One was attempted via `POST /api/generate` with
  `images: [base64]` but got interrupted before confirming output — don't assume it works,
  smoke-test it as the very first step of building Stage 4.

## Decisions made (don't re-litigate without reason)
- **Stage 4 routing: call Ollama directly first**, not through Respan — explicitly decided because
  Respan/Nango/Lambda keys don't exist yet and there's no reason to block progress on that. Wire
  Respan routing in afterward as a small change (swap the HTTP call, using
  `examples/respan-call.py` as the interface reference), tagged `stage=extract`/`stage=crosscheck`
  + `doc_type` per the Respan rubric line (see `.claude/agents/respan-call-auditor`).
- **OCR confident-word threshold is 6, not the CLAUDE.md-stated default of 8** — changed after
  needle `screenshot_03` (a genuine 7-word short text) was being wrongly dropped. Don't revert this
  without re-checking that needle.
- **Don't merge `build-pipeline` → `main` yet** — no ingest, extraction, storage, or UI exists end
  to end; wait for a coherent demoable slice (Stage 4 working is the next natural checkpoint).

## Gotchas / non-obvious things worth knowing before touching these files
- `pipeline/ocr_gate.py` crops every image to its content bounding box (+ padding, + a
  background-colored border) before running tesseract. This isn't cosmetic — tesseract's automatic
  page-layout analysis was found (via needle `screenshot_03`) to silently drop entire text blocks
  on images that are mostly blank margin around a small amount of content. Don't remove the crop
  step to "simplify" the code; it's a real correctness fix, documented inline and in `plan.md`
  Phase 5.
- The needle PNGs are gitignored (`*.png`) — if `git status` ever shows them as untracked after
  running the generator, that's expected, not a bug. Don't `git add -f` them; see the README setup
  step instead.
- No `.env` file exists on the original machine either — every command run so far (metadata gate,
  OCR gate) needed zero API keys. Only Stage 4 (Ollama, local, no key needed) and later Stage
  1's Gmail half / Stage 5 (need real keys) change that.

## Immediate next step: build Stage 4 (`pipeline/extract.py`)

1. **Smoke-test first**, don't assume: one `POST http://localhost:11434/api/generate` call with
   `model: "gemma4:e4b"`, `images: [base64 of a needle receipt]`, a simple prompt — confirm you get
   a real response and note the latency (this is also the Phase 1 stage-4 timing number `plan.md`
   is waiting on).
2. Build `extract.py`: takes an image path + the OCR text hint from Stage 3, sends both to
   `gemma4:e4b` via Ollama's REST API, requests strict JSON (Ollama supports `"format"` as a JSON
   schema for constrained decoding — use it, per `CLAUDE.md`'s "strict JSON" constraint), parses
   the response, **retries once on parse failure, drops the record on a second failure** — one bad
   response must never stall the batch.
3. Schema is in `CLAUDE.md` under "Data model" — `doc_type`, `title`, `date`, `amount`, `currency`,
   `entity`, `identifiers`, `key_values`, `summary`. **Null over guessing, always** — this is
   checked by the `.claude/agents/schema-guard` subagent, run it after building this.
4. Validate against the 12 needles expected to reach `extracted` (see `tests/needles/manifest.json`)
   — chain metadata gate → OCR gate → extract, same pattern as `ocr_gate.py`'s `__main__` block.
5. Once Stage 4 works, `.claude/skills/pipeline-throughput` can finally run for real (it refuses to
   run until stage 2-3 AND stage 4 code both exist) — that gives the formal 800-vs-300 image cap
   decision `plan.md` Phase 1 is still waiting on. Run it and record the result in `plan.md`.

## Plan.md phase status (snapshot)

| Phase | Status |
|---|---|
| 0 — Env & keys | Partial: fake Gmail account exists; vision model downloaded & confirmed vision-capable. Nango/Respan/Lambda keys still not set up — no `.env` yet. |
| 1 — Throughput spike | Stage 2-3 numbers in hand. Stage 4 timing + formal cap decision blocked on Stage 4 existing. |
| 2 — Repo scaffolding | Done. |
| 3 — Stage 1 Ingest | Not built. Local-photo-folder half is unblocked (no keys needed); Gmail half needs Nango. |
| 4 — Stage 2 Metadata gate | **Done.** |
| 5 — Stage 3 OCR gate | **Done.** |
| 6 — Stage 4 Extract | **Not built — the immediate next step, see above.** |
| 7 — Stage 5 Cross-check | Blocked on Lambda/Respan provisioning (have the call interface now, via `examples/respan-call.py`; no key yet). |
| 8 — Stage 6 Store & search | Schema written, no insert/query code yet. |
| 9 — API + Web UI | Not started. |
| 10 — Needle test validation | Stages 2-3 validated individually. Full skill run needs stages 4-6. |
| 11 — Demo prep | Not started. |
