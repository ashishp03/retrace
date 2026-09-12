---
name: needle-test
description: Re-run the fifteen-needle regression check against the current Retrace pipeline and report pass/fail per needle doc
disable-model-invocation: true
---

# needle-test

Retrace's testing strategy (see `CLAUDE.md`) is fifteen known "needle" documents planted in the ingest folder, re-checked after every pipeline change — not a formal benchmark. This skill runs that check.

## Convention this skill expects

- `tests/needles/manifest.json` — a list of needle docs, each with:
  - `file`: path to the needle file (relative to `tests/needles/docs/`)
  - `expected_outcome`: one of `"extracted"` (should reach stage 6 with fields) or `"dropped_at_metadata"` / `"dropped_at_ocr"` (should be filtered before extraction — negative needles that prove the gates actually gate)
  - `expected_fields` (when `extracted`): the subset of the stage-4 JSON schema fields this needle should produce (e.g. `{"doc_type": "receipt", "amount": 18.50}`) — `null` fields are expected to stay `null`, not be guessed
- `tests/needles/docs/` — the actual fifteen files
- A pipeline entrypoint that can run stages 2-6 against a single file or a small directory and emit the resulting record(s) as JSON (however Phase 2-8 of `plan.md` ends up exposing it — a CLI, a module function, whatever exists at the time this skill runs)

If either the manifest or a runnable pipeline entrypoint doesn't exist yet, **say so explicitly and stop** — don't fabricate a pass/fail report.

## What to do when invoked

1. Read `tests/needles/manifest.json`. If missing, report that the needle set hasn't been created yet (this is Phase 10 of `plan.md`) and stop.
2. For each needle doc, run it through the pipeline (stages 2 through 6, or as far as the current codebase implements) and capture the actual outcome.
3. Compare actual vs. expected:
   - For `dropped_at_*` needles: confirm it was actually dropped at that gate, not an earlier or later one — dropped-for-the-wrong-reason is still a bug.
   - For `extracted` needles: confirm `doc_type` matches, confirm every field in `expected_fields` matches (exact match for scalars, presence check for `key_values`/`identifiers`), and confirm no field that should be `null` came back guessed.
4. Report a table: needle file → expected → actual → pass/fail. Summarize as `N/15 passing`.
5. For failures, show the actual JSON returned (or the actual gate it was dropped at) so the failure is diagnosable without re-running manually.

## Notes

- This is meant to be cheap to re-run — don't add caching, don't skip needles that passed last time. Every invocation is a full 15-needle run.
- If the pipeline changes shape (new stage, new schema field), update `manifest.json` first, then re-run — this skill doesn't infer expectations, it checks against what's declared.
