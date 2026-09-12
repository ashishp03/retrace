# retrace

Everyone's documents are scattered across a camera roll and an inbox, and none of them are searchable. Retrace reads all of it locally, pulls out the structured content, and makes it queryable, with a second model checking the first one's work.

Built for the Open Model Hack (2 people, 10:30–16:30, judged live).

## Setup

Dependencies and the Python version are managed with [`uv`](https://docs.astral.sh/uv/) — no manual `venv`/`pip` steps.

1. Install `uv` if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`)
2. Clone the repo, then from its root:
   ```bash
   uv sync
   ```
   This creates `.venv/`, installs the exact pinned versions from `uv.lock`, and installs the Python version pinned in `.python-version` (3.12) if you don't already have it.
3. Copy the secrets template and fill in your own keys — never commit `.env`:
   ```bash
   cp .env.example .env
   ```
   `.env` holds Nango, Respan, and Lambda credentials plus local paths (photo folder, DB path, Ollama host/model). A `.claude/` hook blocks direct edits/commits of `.env` from inside Claude Code — edit it by hand.
4. Generate the fifteen synthetic needle-test documents — these are **not** committed (generated,
   not source), so this step is required after every fresh clone:
   ```bash
   uv run python tests/needles/generate_needles.py
   ```
   Re-run any time to regenerate deterministically; see `tests/needles/manifest.json` for the
   expected outcome of each one and `.claude/skills/needle-test` for the check that uses them.
5. External runtime dependencies (not managed by `uv`): [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract`) for stage 3, and [Ollama](https://ollama.com) for the local stage-4 vision model.

Adding a dependency later: `uv add <package>` (or `uv add --group dev <package>` for dev-only tools) — this updates both `pyproject.toml` and `uv.lock` together, so always commit both.

## Docs

- [`CLAUDE.md`](./CLAUDE.md) — full scope contract, the six-stage extraction cascade, data model, judging rubric, and the open setup questions still to be resolved
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — mermaid diagrams: the pipeline funnel and the local/cloud component + network boundary
- [`plan.md`](./plan.md) — step-by-step build plan, Phase 0 (keys/environment) through Phase 11 (demo prep), including the default resolutions assumed for each open question

## Project-local automation

`.claude/` in this repo adds a few things scoped to this build:
- `skills/needle-test`, `skills/pipeline-throughput` — re-runnable checks described in `plan.md`
- `agents/schema-guard`, `agents/respan-call-auditor` — reviewers for the null-over-guess data rule and the Respan call-tagging rubric line
- `settings.json` hooks — block direct edits to `.env`, and block `git add`/`git commit` from staging `.env` or the local image staging directory
