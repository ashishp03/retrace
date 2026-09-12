# Retrace — Checkpoint (1hr-to-go session)

Short version of `summary.md`'s update section — read this first, go there for detail.

## What just happened

Keys went live mid-hackathon (Respan key provided, `gemma4:e4b` pulled into local Ollama), so
Stages 4–6 got built and validated against all 15 needle docs in one pass:

| Stage | File | What it does | Result |
|---|---|---|---|
| 4 — Extract | `pipeline/extract.py` | Local Ollama (`gemma4:e4b`) vision call + OCR hint → strict JSON, retry-once-then-drop | 12/12 expected needles extracted, exact field match, ~3.0s/image |
| 5 — Cross-check | `pipeline/crosscheck.py` | Second model via **Respan**, tagged `stage=crosscheck`+`doc_type`, field-diffed against stage 4 | 9 `high` / 3 `flagged` — all 3 flags are the `card` needles (real disagreement on `entity`, one on `doc_type`) |
| 6 — Store & search | `pipeline/store.py` | Inserts into SQLite + FTS5 (`pipeline/schema.sql`), CLI search helper | 12 stored, 3 correctly dropped (2 metadata, 1 OCR), 3 sample FTS queries all correct |

Full chain: `uv run python pipeline/store.py tests/needles/docs` runs stages 2→6 end to end and
prints results + sample searches.

`.env` now has a real `RESPAN_API_KEY` and `OLLAMA_VISION_MODEL=gemma4:e4b`.

## The one gap you need to know for Q&A

CLAUDE.md requires stage 5 to be **a Gemma checkpoint served from Lambda** (that's a mandatory
rubric line + the bonus). Checked Respan's live `/models` list — **no Gemma entries, no Lambda
endpoint provisioned.** Stage 5 currently verifies against `anthropic/claude-haiku-4-5` through
Respan instead. This still earns "Respan use" and "multi-agent coordination," but **not** the
Lambda / Gemma-on-Lambda lines. It's a config swap, not a rewrite — `RESPAN_CROSSCHECK_MODEL` in
`.env` — the moment a Lambda-hosted Gemma endpoint exists. Decide now whether that's worth
attempting in remaining time, or whether to just own the gap verbally in Q&A.

## What's left to understand / decide to finish

1. **Lambda/Gemma decision (above)** — attempt it, or accept and script the Q&A answer.
2. **No ingest code yet** (`ingest/` is empty) — everything so far ran directly against
   `tests/needles/docs`, not a real photo folder or Gmail. Need: a folder walker (HEIC→JPEG via
   `pillow-heif`, tag `source=photos`) before this is demoable on real data. Gmail/Nango ingest is
   separate and currently has no key — lowest priority if time is this short.
3. **No web UI** (`web/`, `api/` are empty) — right now "search" is a CLI script. Decide: is a
   bare HTML page + one FastAPI `/search` endpoint feasible in remaining time, or does the demo
   show the terminal output directly? This is the biggest visible gap for a live demo.
4. **800-vs-300 image cap** — never formally decided, but the real numbers now exist: ~2.5ms/image
   (stages 2–3) + ~3s/image on the ~20% surviving to stage 4 (12/15 needles, admittedly a biased
   sample — real photo libraries will have a much lower survival rate, closer to the ~5% CLAUDE.md
   assumes). Do the arithmetic once you know the real folder size; don't extrapolate off needles
   alone.
5. **Demo script** — pick the 2–3 search queries to actually run live, and decide whether to show
   a flagged `card` result on purpose (it's a genuinely good multi-agent story, not staged).

## Quick commands

```bash
# regenerate needle images if missing
uv run python tests/needles/generate_needles.py

# full pipeline over needles, prints stored docs + 3 sample searches
uv run python pipeline/store.py tests/needles/docs

# stage 4 only, verbose per-image output
uv run python pipeline/extract.py tests/needles/docs

# stage 5 only, shows agreement + diffs per image
uv run python pipeline/crosscheck.py tests/needles/docs
```
