# pipeline/ — Stages 2–5: Gates, Extract, Cross-check

> Local goals and scope for this folder. Root [`../CLAUDE.md`](../CLAUDE.md) is the source of
> truth for the six-stage architecture table, data model, and constraints — read it first.

**Role:** The cascade that protects the expensive vision call. Stages 2–3 exist purely to keep
stage 4's input small; stage 5 is the multi-agent agreement check.

| Stage | What runs here |
|---|---|
| 2 — Metadata gate | Filename heuristics, EXIF, aspect ratio, dimensions. No model. Loose by design — filters, doesn't decide. |
| 3 — OCR gate | Tesseract over survivors; drop anything under the confident-word threshold (start at 8). Keep the OCR text — reused as a stage-4 hint and search fallback. |
| 4 — Extract | Gemma 4 vision on image + OCR hint, one call, one strict JSON object per the root data model. Should hit ~5% of the library. |
| 5 — Cross-check | Second, larger Gemma checkpoint via **Respan**, hosted on **Lambda**, diffed field-by-field against stage 4's output on a sampled subset. |

**Not yet built.** Blocked on open questions in the root `CLAUDE.md`: how Gemma 4 vision is
served for stage 4 (local stack vs. Respan), and the Lambda deployment shape for stage 5.

**Sequencing:** stand up the Lambda endpoint for stage 5 and confirm Nango/Respan keys work in
the **first 30 minutes** — not after the extraction pipeline is built. Time one image through
stage 4 and fifty images through stages 2–3 before writing anything else; those two numbers decide
whether the 800-image cap holds or needs to drop to 300.

**Constraints:**
- Strict JSON only. Use constrained/schema-forced decoding if the stack supports it; otherwise a
  strict parser that retries once and drops the record on a second failure — one bad response must
  never stall the batch.
- The model returns `null` rather than guessing — a confidently wrong field is worse than a blank
  one.
- Tag every Respan-routed call by stage and `doc_type` (see `respan-call-auditor` agent) so cost
  and latency read straight off the dashboard.
- Agreement from stage 5 is `"high"` or `"flagged"` — disagreement routes to a human review queue,
  it doesn't block storage.
