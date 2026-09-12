# Retrace

**One sentence:** everyone's documents are scattered across a camera roll and an inbox, and none of them are searchable — Retrace reads all of it locally, pulls out the structured content, and makes it queryable, with a second model checking the first one's work.

Built for the **Open Model Hack** — 2 people, 10:30–16:30, judged live (3-min demo + 2-min Q&A), top 3 win.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the system diagrams.

---

## Scope contract — binding for today

### In scope (all of it has to ship)

- Two ingestion sources: a local photo folder, and Gmail attachments pulled via Nango
- Hard cap: most recent 800 images, stated openly in the demo
- Four document types only: `receipt`, `card/ID`, `form/letter`, `screenshot-of-text`
- A cheap OCR gate that runs before the vision model ever sees an image
- A two-model agreement check as the confidence signal (the multi-agent story)
- The larger verifier model (stage 5) served from **Lambda** — mandatory, not a stretch goal
- SQLite + full-text search (FTS5), one search page

### Out of scope — push back if this drifts in

- No fine-tuning, no LoRA, no training anything
- No vector database, no embeddings, no semantic search
- No mobile app — it's a local web page
- No auth, no accounts, no multi-user
- No Drive, Dropbox, or a third source — Gmail only
- No editing or exporting records — read-only

---

## Architecture — a six-stage cascade

The whole design turns on one number: a vision model over a few thousand images is too slow for a single day, so almost nothing should reach it. **Stages 2 and 3 exist purely to protect stage 4.**

Build in this order, and measure throughput in the **first 30 minutes** before writing anything else:
- One image timed end-to-end through stage 4
- Fifty images timed through stages 2–3

Those two numbers decide whether the 800-image cap is realistic or needs to drop to 300.

| # | Stage | Cost | What it does |
|---|-------|------|---------------|
| 1 | **Ingest** | seconds/image | Point at a local folder; decode HEIC → JPEG up front with `pillow-heif`. In parallel, Nango pulls Gmail attachments (images + PDFs) into the same staging directory. Every file lands tagged `photos` \| `gmail`. |
| 2 | **Metadata gate** | ~0 ms/image, no model | Filename heuristics, EXIF, aspect ratio, dimensions — cheaply demote obvious non-documents (blurry, very wide, tiny). Loose by design: its job is to filter, not decide. |
| 3 | **OCR gate** | ~100–300 ms/image | Tesseract over survivors; count confident words, drop anything under threshold (start at 8 words). Keep the OCR text — reused as a stage-4 hint and as search fallback. |
| 4 | **Extract** | ~1–3 s/image, should hit ~5% of the library | Gemma 4 vision on the image + OCR text as a hint, one call, returns one strict JSON object (schema below). Classifies doc type and pulls fields in the same pass. |
| 5 | **Cross-check** | on a sampled subset | Same image routed to a second, larger Gemma checkpoint through **Respan**, hosted on **Lambda**, diffed field-by-field against stage 4's output. Agreement = high confidence; disagreement flags the record for human review. Must be a Gemma checkpoint on Lambda — satisfies both the Lambda rubric line and the Gemma-on-Lambda bonus in one deployment decision. |
| 6 | **Store & search** | instant | SQLite with an FTS5 virtual table over extracted fields + OCR text. No vector DB. |

**Sequencing implication:** stand up the Lambda endpoint for the larger Gemma checkpoint in the first 30 minutes, alongside getting Nango and Respan keys working — not late in the day. It gates two rubric lines and the bonus at once; a cold model server discovered at hour four is the worst way to lose points here.

---

## Data model

One table, one schema, no negotiation once agreed.

```jsonc
// one row per document found — produced by the model
{
  "doc_type": "receipt" | "card" | "form" | "screenshot_text",
  "title": "Blue Bottle Coffee — 14 Aug 2026",
  "date": "2026-08-14",              // null if absent, never guessed
  "amount": 18.50,                    // receipts only
  "currency": "USD",
  "entity": "Blue Bottle Coffee",     // merchant, issuer, sender
  "identifiers": ["policy #A4471-B"], // card/policy/account numbers
  "key_values": { "expires": "2029-03" },
  "summary": "one sentence, what this is"
}
```

```jsonc
// added by the pipeline, not the model
{
  "source": "photos" | "gmail",
  "file_path": "...",
  "taken_at": "...",
  "ocr_text": "...",
  "agreement": "high" | "flagged"     // from stage 5
}
```

**Rule:** the extraction model returns `null` rather than guessing. A confidently wrong date is worse than a blank one.

---

## Judging rubric — what's actually being scored

| Rubric line | Where it shows up |
|---|---|
| Nango API use | Gmail attachment ingestion (stage 1) — second source, biggest prize |
| Lambda — host an open model | Stage 5's larger verifier, served from a Lambda endpoint — mandatory |
| Respan use | Routes both extraction calls (stages 4–5); tag every call by stage/doc type so cost and latency read straight off the dashboard |
| Multi-agent coordination | The two-model agreement check — a second model checks the first, disagreement routes to a human review queue |
| Commercial viability | Not a build item — a rehearsed Q&A answer (who buys it, why local-only is the sellable feature, what you'd add) |
| Bonus — Gemma on Lambda | Free with the Lambda line, as long as that hosted model is Gemma |

---

## Constraints that matter for how this gets built

- **Network-off demo:** everything must work with the network off at demo time except the Nango sync and the Respan-routed Lambda call for stage 5 — venue wifi is a named risk. Pre-index before demos.
- **Strict JSON:** the model must return strict JSON. Use constrained/schema-forced decoding if the serving stack supports it; otherwise a strict parser that retries once and drops the record on a second failure. One bad response must never stall the batch.
- **Bias toward the smallest thing that works.** This is a two-person, ~5.5-hour build. If about to add infrastructure not in this spec (a queue, a second database, a config system), say so and ask before adding it.
- **Testing = fifteen "needle" documents** planted in the folder, re-checked after every change — not a formal benchmark. Build ingestion so this is trivial to re-run.

---

## Open questions — resolve before scaffolding or writing code

These are unanswered. Do not assume defaults on the ones that change file layout or dependencies — confirm with the user first.

**Runtime & serving**
1. How does Gemma 4 vision actually run for stage 4 — a local serving stack (Ollama, llama.cpp/LM Studio, vLLM, MLX), or also through Respan? What's already installed on this machine, and is there local GPU access, or is everything model-serving-side going through Respan/Lambda?
2. For the stage-5 Lambda deployment: spinning up a Lambda GPU instance ourselves (which image/template, how the serving stack gets deployed), or using a Lambda-hosted inference API endpoint if one exists for Gemma? Is there already a Lambda account/API key, or does one need provisioning?

**Integrations**
3. Are there existing Nango and Respan accounts and API keys, or do they need to be created (including OAuth app setup for Gmail)? Which Google account should the Gmail sync test against?
4. Any existing Respan project/routing config to reuse, or created from scratch?

**Application shape**
5. Backend language/framework — Python with FastAPI/Flask (matches `pytesseract`/`pillow-heif`/`sqlite3` naturally), or something else?
6. Frontend for the single search page — plain HTML/JS/CSS served by the backend, or a lightweight framework? Default is the simplest option given "no mobile app, it's a local web page," unless something specific is wanted.
7. How should indexing run — CLI/script triggered on demand, or a background worker with a progress endpoint the UI polls (spec calls for a live progress counter during the demo)?
8. ~~Repo/folder structure~~ — **Resolved:** one project, split by pipeline stage: `ingest/` (stage 1), `pipeline/` (stages 2–5), `api/` (stage 6 + serving), `web/` (search page). Each has its own `CLAUDE.md`.

**Data & secrets**
9. Where do API keys/secrets live — a `.env` file? Already set up, or scaffold it with a `.env.example`?
10. Is there a real photo folder and Gmail inbox to point at during setup, or build against synthetic/sample documents until those are ready?

**Testing & demo**
11. Should the fifteen-needle test be an actual automated script (ready to re-run all day), or a manual checklist run by hand?
12. Anything about the demo flow (the folder actually demoed, the three search queries) worth locking in now so the UI gets built around those exact queries?

Once these are settled, the next step is a short implementation plan mapped to the six-stage architecture above, starting with whatever gates the rubric earliest — Nango auth and the Lambda endpoint for the stage-5 model — before touching the extraction pipeline or UI.
