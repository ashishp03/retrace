# ingest/ — Stage 1: Ingest

> Local goals and scope for this folder. Root [`../CLAUDE.md`](../CLAUDE.md) is the source of
> truth for the overall scope contract, rubric, and constraints — read it first.

**Role:** Get every candidate document — local photos and Gmail attachments — into one staging
directory, tagged by source, before any gate or model touches them.

- Local source: point at a photo folder, decode HEIC → JPEG up front with `pillow-heif`.
- Remote source: Nango pulls Gmail attachments (images + PDFs) in parallel into the same staging
  directory. Gmail only — no Drive, Dropbox, or a third source (see root scope contract).
- Every file lands tagged `photos` | `gmail` — this tag flows through to the final data model as
  `source`.
- Hard cap: most recent 800 images total, across both sources.

**Not yet built.** Blocked on open questions in the root `CLAUDE.md`: which backend
language/framework, whether Nango credentials exist yet, and which real photo folder / Gmail
account to point at for the demo.

**Constraints:**
- The staging directory holds real personal photos/attachments — never commit it. It matches the
  `staging`/`photos` path patterns already blocked by `.claude/hooks/check-git-secrets.sh`.
- Network-off demo: the Nango sync is one of the two things explicitly allowed to need network at
  demo time (the other is the Respan/Lambda call in `pipeline/`) — everything else must pre-index.
