# retrace

Everyone's documents are scattered across a camera roll and an inbox, and none of them are searchable. Retrace reads all of it locally, pulls out the structured content, and makes it queryable, with a second model checking the first one's work.

Built for the Open Model Hack (2 people, 10:30–16:30, judged live).

## Docs

- [`CLAUDE.md`](./CLAUDE.md) — full scope contract, the six-stage extraction cascade, data model, judging rubric, and the open setup questions still to be resolved
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — mermaid diagrams: the pipeline funnel and the local/cloud component + network boundary
- [`plan.md`](./plan.md) — step-by-step build plan, Phase 0 (keys/environment) through Phase 11 (demo prep), including the default resolutions assumed for each open question

## Project-local automation

`.claude/` in this repo adds a few things scoped to this build:
- `skills/needle-test`, `skills/pipeline-throughput` — re-runnable checks described in `plan.md`
- `agents/schema-guard`, `agents/respan-call-auditor` — reviewers for the null-over-guess data rule and the Respan call-tagging rubric line
- `settings.json` hooks — block direct edits to `.env`, and block `git add`/`git commit` from staging `.env` or the local image staging directory
