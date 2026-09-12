# Retrace — 3-minute demo script

Timed to ~2:55 total, leaving a little slack. Speaker split is a suggestion, not a requirement —
swap freely. Stage directions in **bold brackets**.

Pre-demo checklist (do this before you're on stage, not during):
- [ ] API server running (`uv run uvicorn api.main:app --host 127.0.0.1 --port 8000`), UI open at `http://127.0.0.1:8000`
- [ ] Lambda SSH tunnel alive (`curl http://localhost:11435/api/version`)
- [ ] Gmail already synced at least once (Sync button can still be clicked live, but don't depend on it)
- [ ] Confirm the two image questions and two Gmail questions below still return good answers against the current DB — re-run them once right before you go up

---

### 1. Intro — 0:00–0:15 (15s)

**[NIKHIL, standing, no slide yet]**

> "Everyone's important documents are scattered across two places nobody can search: their
> camera roll and their inbox. Retrace reads both, locally, and lets you just ask — in plain
> English — instead of scrolling."

---

### 2. Architecture slide — 0:15–0:50 (35s)

**[Flash the simplified diagram from the README]**

> "Five steps. Photos and Gmail attachments come in — cheap filters throw out anything that's
> not actually a document before we spend money on a model. What survives goes to a local
> Gemma model that reads it and pulls out the fields. A second, bigger Gemma — hosted on a
> Lambda GPU — independently double-checks that read. If they disagree, a third model, routed
> through Respan, steps in to arbitrate — resolve it, or flag it for a human. Everything lands
> in a local database you can just ask questions against."

*(Say it fast — this is the one part of the demo that's information-dense, everything after is
just watching it work.)*

---

### 3. Switch to the UI — 0:50–0:55 (5s)

**[ASHISH takes over, switches the shared screen to `localhost:8000`]**

> "Let's just use it."

---

### 4. Two questions from local photos — 0:55–1:35 (40s)

**[ASHISH types, NIKHIL narrates the result if useful]**

**Q1:** *"Can you give me a total summary of how much I spent on coffee"*
- Expect: cites the Blue Bottle Coffee receipt, correct dollar amount, shows the source card
  underneath with the "Verified" seal.

**Q2:** *"When did Dean and Martinez renew their lease?"*
- Expect: correct renewal date, cites the actual lease notice document.

> "Notice it's not just search — it's reading the actual field, and showing you which document
> it came from, and whether both models agreed on it."

---

### 5. Show the real Gmail inbox — 1:35–1:50 (15s)

**[Switch tabs to Ashish's real Gmail inbox — ashiram12309@gmail.com]**

> "This is a real inbox — receipts and letters sent in as plain image attachments, nothing
> staged. Retrace pulls these in through Nango."

**[Switch back to Retrace. Optionally click "Sync Gmail" live if you're confident in wifi —
otherwise skip the click and just say it's already synced.]**

---

### 6. Two questions from Gmail — 1:50–2:30 (40s)

**Q3:** *"What did Henry-Johnson Bank tell me about my account?"*
- Expect: cites the Account Change Notice, account ending, source tag reads "Gmail."

**Q4:** *"How much do I owe Stephanie Gibson Consulting?"*
- Expect: exact invoice amount, date, invoice number, source tag "Gmail."

> "Same pipeline, same two-model check, same search — it just doesn't care whether the document
> came from your camera roll or your inbox."

---

### Close — 2:30–2:55 (25s)

**[NIKHIL]**

> "Everything you just saw runs offline except two calls — the Gmail sync, and that
> cross-check. No vector database, no cloud storage of your documents, nothing leaves this
> machine except the one field-level check. That's the pitch: local-first isn't a limitation
> here, it's the product."

---

## Backup answers (if live network hiccups)

If the Lambda tunnel or Respan is down when a flagged/arbitration case would normally show up,
stick to documents you already know return `agreement: high` cleanly (both coffee/lease
questions above do). Don't demo a flagged/arbitrated document live unless you've tested it
minutes before — that's the one path with an extra network hop and more variance.
