# Retrace — System Architecture

Two views of the same system: the **pipeline** (how a file becomes a searchable record) and the **components** (what runs where, and which side of the network boundary it's on). See [`CLAUDE.md`](./CLAUDE.md) for the full spec, data model, and judging rubric.

---

## 1. Pipeline — the six-stage cascade

The funnel is the point: a vision model over a few thousand images is too slow for one day, so stages 2–3 exist purely to keep volume off stage 4. Roughly 800 candidates should narrow to ~5% (~40 images) by the time they reach extraction.

```mermaid
flowchart TD
    subgraph SRC["Sources"]
        A1["Local photo folder\n(HEIC → JPEG via pillow-heif)"]
        A2["Gmail attachments\nvia Nango"]
    end

    A1 --> B["Stage 1 — Ingest\nseconds/image · tag source: photos | gmail\nstaging directory"]
    A2 --> B

    B --> C["Stage 2 — Metadata gate\n~0 ms/image · no model\nfilename / EXIF / aspect ratio / dimensions"]
    C -->|demoted: blurry, tiny, very wide| C_DROP(["dropped\n(not indexed)"])
    C -->|survives, loose filter| D

    D["Stage 3 — OCR gate\n~100-300 ms/image · Tesseract\ncount confident words, threshold ~8"]
    D -->|below word threshold| D_DROP(["dropped\nOCR text still kept as fallback"])
    D -->|survives ~5% of original 800| E

    E["Stage 4 — Extract\n~1-3 s/image · Gemma 4 vision\nimage + OCR hint → ONE strict JSON object\nclassifies doc_type + pulls fields"]
    E --> E2{"strict JSON\nparsed OK?"}
    E2 -->|fails twice| E_DROP(["record dropped\nbatch continues"])
    E2 -->|ok| F

    F["Stage 5 — Cross-check\nsampled subset · routed via Respan\nlarger Gemma checkpoint, hosted on Lambda\nfield-by-field diff vs stage 4"]
    F -->|fields match| G1["agreement: high"]
    F -->|fields differ| G2["agreement: flagged\n→ human review queue"]

    G1 --> H
    G2 --> H

    H["Stage 6 — Store & search\nSQLite + FTS5 virtual table\nover extracted fields + ocr_text\nNO vector DB"]
    H --> I["Search page\n(single web page, read-only)"]

    style E fill:#f9d5a7,stroke:#c77b1e
    style F fill:#f4b8b8,stroke:#c0392b
    style H fill:#b8e0d2,stroke:#1e8c5a
```

**Reading the colors:** orange (stage 4) and red (stage 5) are the only stages that touch a model — everything before them is free/cheap filtering, and everything after them is instant local storage.

---

## 2. Components & network boundary

This is the diagram that makes the demo-day constraint concrete: **everything must run with the network off except the Nango sync and the Respan-routed Lambda call for stage 5.** Pre-index before demos so this boundary is never tested live.

```mermaid
flowchart LR
    subgraph LOCAL["Local machine — works with network OFF"]
        direction TB
        PF["Local photo folder"]
        STG["Staging directory\n(source-tagged files)"]
        META["Metadata gate\n(stage 2)"]
        OCR["Tesseract OCR gate\n(stage 3)"]
        GEMMA4["Gemma 4 vision\nlocal serving\n(stage 4 — extract)"]
        DB[("SQLite + FTS5")]
        WEB["Web UI\nsingle search page"]

        PF --> STG --> META --> OCR --> GEMMA4 --> DB
        WEB <--> DB
    end

    subgraph CLOUD["Cloud — network REQUIRED"]
        direction TB
        NANGO["Nango\nGmail OAuth + attachment sync"]
        RESPAN["Respan\nroutes + tags calls by stage/doc_type"]
        LAMBDA["Lambda-hosted endpoint\nlarger Gemma checkpoint\n(stage 5 — cross-check verifier)"]

        RESPAN --> LAMBDA
    end

    GMAIL["Gmail inbox"] --> NANGO --> STG
    GEMMA4 -. "sampled subset,\nfield-by-field diff" .-> RESPAN
    LAMBDA -. "agreement: high | flagged" .-> DB

    style CLOUD fill:#fde3e3,stroke:#c0392b,stroke-width:2px
    style LOCAL fill:#e3f2e8,stroke:#1e8c5a,stroke-width:2px
    style LAMBDA fill:#f4b8b8,stroke:#c0392b
```

**Rubric mapping onto this diagram:**

| Rubric line | Component |
|---|---|
| Nango API use | `Gmail inbox → Nango → staging directory` |
| Lambda — host an open model | `Lambda-hosted endpoint` (must be the Gemma checkpoint used in stage 5) |
| Respan use | `Respan` node — routes/tags both the stage-4 and stage-5 model calls |
| Multi-agent coordination | `Gemma 4 vision (stage 4)` vs. `Lambda Gemma checkpoint (stage 5)` agreement diff, flagged records → review queue |
| Bonus — Gemma on Lambda | Satisfied automatically if `LAMBDA` node is a Gemma checkpoint |

---

## Open items that affect these diagrams

The **Runtime & serving** and **Application shape** questions in `CLAUDE.md` (local serving stack choice, backend framework, background-worker vs. CLI indexing) will refine box-level detail here but not the overall shape — the source → gates → extract → cross-check → store funnel and the local/cloud network split are fixed by the scope contract and should not change once implementation starts.
