# Retrace — Checkpoint 2

Supersedes `CHECKPOINT.md`'s architecture section — stage 5 and the Lambda/Respan wiring changed
significantly since then. Read this for current state; `summary.md` still has the full narrative
history if you need it.

## System architecture (current)

### Pipeline overview

```
 Local photo folder ---\
                         >--> [staging dir, tagged photos|gmail] --(1)
 Gmail via Nango -------/                                            |
                                                                       v
                                                     +---------------------------------+
                                                     | Stage 2: Metadata gate           |
                                                     | filename / EXIF / aspect ratio    |
                                                     | no model, ~2.5ms/image            |
                                                     +---------------------------------+
                                                        |survives              |demoted
                                                        v                      v
                                       +---------------------------+     [ dropped ]
                                       | Stage 3: OCR gate          |
                                       | tesseract, ~108ms/image    |
                                       +---------------------------+
                                          |survives          |dropped
                                          v                   v
                          +---------------------------+  [ dropped ]
                          | Stage 4: Extract           |
                          | local gemma4:e4b (Ollama)  |
                          +---------------------------+
                                          |
                                          v
                          +---------------------------+
                          | Stage 5: Cross-check       |   <-- see detail below
                          +---------------------------+
                                          |
                                          v
                          +---------------------------+
                          | Stage 6: Store & search     |
                          | SQLite + FTS5                |
                          +---------------------------+
                                          |
                                          v
                          +---------------------------+
                          | Web search UI (not built)   |
                          +---------------------------+

(1) Stage 1 — Ingest — not built yet.
```

### Stage 5 detail — cross-check (extractor -> verifier -> conditional arbiter)

```
  Stage 4 output
  (local gemma4:e4b fields)
        |
        v
  +--------------------------------------+
  | Verifier: gemma3:27b                 |
  | on Lambda GPU instance (A100 40GB)    |
  | reached over an SSH tunnel            |
  +--------------------------------------+
        |
        v
  Fields agree with stage 4?
        |
        +--yes (usually)--> agreement = high ---------+
        |                                              |
        no                                             |
        |                                              v
        v                                       +-------------+
  +--------------------------------------+      | Stage 6:    |
  | Arbiter (conditional only):           |      | Store       |
  | claude-haiku-4-5 via Respan            |      +-------------+
  | text-only -- reasons over both               ^
  | extractions + OCR text, no image             |
  +--------------------------------------+       |
        |                                        |
        v                                        |
  agreement = high or flagged                    |
  + resolution + reasoning  ----------------------+
```

**Why the arbiter is conditional, not a third parallel vote:** two independent models reading a
clear document should usually agree — running a third model unconditionally just to triple-check
agreement wastes a call most of the time and doesn't add a distinct capability. The arbiter is
dispatched only on actual disagreement (5/12 needles in the last full run) and its job is
categorically different from the other two: it never sees the image, it reasons over two
conflicting JSON extractions + the OCR text and decides a resolution or an escalation. That's the
real "multi-agent coordination" story — a router deciding when a specialist needs to get involved,
not three models doing the same job and voting.

## Status per stage

| Stage | Model / infra | Status |
|---|---|---|
| 1 — Ingest | local folder walker + Nango (Gmail) | **Not built.** Nango key now in `.env`; see setup section below. |
| 2 — Metadata gate | none | Done, validated (13/15 needles) |
| 3 — OCR gate | tesseract | Done, validated (12/15 needles) |
| 4 — Extract | `gemma4:e4b`, local Ollama | Done, validated (12/12 expected needles) |
| 5 — Cross-check (verifier) | `gemma3:27b`, Ollama on Lambda GPU (A100 40GB, `us-west-2`) | Done, validated — reached via SSH tunnel `localhost:11435` → remote `11434` |
| 5 — Cross-check (arbiter) | `anthropic/claude-haiku-4-5` via Respan | Done, validated — tagged `stage=crosscheck`, `role=arbiter`, `doc_type` |
| 6 — Store & search | SQLite + FTS5 | Done, validated (12 stored, 3 correctly dropped, sample queries correct) |
| API + Web UI | FastAPI + static HTML | **Not built.** Biggest remaining visible gap for a live demo. |

## Infra notes worth remembering

- **Lambda instance**: `129.146.65.187`, `us-west-2`, 1x A100 (40GB SXM4), $1.99/hr, billing while
  running — terminate it when done for the day.
- **SSH tunnel**: `ssh -i ~/Downloads/retrace-lambda-ssh-key-v1.pem -N -L 11435:localhost:11434 ubuntu@129.146.65.187`,
  running via `nohup`+`disown` so it survives tool-call boundaries. It has died once already — if a
  crosscheck run gets `Connection refused` on the Lambda verifier, that tunnel is why; just restart it.
- **Lambda guest agent** is installed on the instance — the Lambda Cloud console should now show
  live GPU/VRAM utilization graphs for it (may take ~1 min to populate after install).
- All 5 pipeline scripts (`metadata_gate.py`, `ocr_gate.py`, `extract.py`, `crosscheck.py`,
  `store.py`) write their results to `outputs/<stage>/results.json` on every run — that's where to
  look for per-document disagreements, arbiter reasoning, and stored records.

---

## Nango setup — what you need to configure, and why

You have a Nango secret key now (`NANGO_SECRET_KEY` — added to `.env`). That authenticates *your*
backend to Nango, but Nango still needs to know how to talk to Google on your behalf, and it needs
an authorized connection to the specific Gmail account before any code can pull attachments. Three
things are missing before `ingest`'s Gmail half can be built:

### 1. A Google Cloud OAuth app (you have to do this in Google Cloud Console)

Nango needs its own OAuth client registered with Google — there's no shared/test credential Nango
provides for Gmail specifically (some providers have one, Gmail doesn't).

1. Create (or select) a project at [console.cloud.google.com](https://console.cloud.google.com).
2. **APIs & Services → Library** → search "Gmail API" → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - Audience: **External**.
   - Add app name + your support email.
   - Under **Data Access / Scopes**, add `https://www.googleapis.com/auth/gmail.readonly` — this
     is all we need (read-only access to list messages and fetch attachments; no need for
     `gmail.modify` or broader scopes since Retrace is read-only end to end).
   - Under **Test users**, add the exact Gmail address you're going to sync
     (**nikhilram@gmail.com**, per your account context) — `gmail.readonly` is a Google
     "restricted" scope, so while the app is in Testing mode (which is fine for a hackathon —
     no security review needed), only addresses explicitly listed as test users can authorize it.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Authorized redirect URI: **`https://api.nango.dev/oauth/callback`** — this is Nango's fixed
     callback, not something you choose.
   - Save the **Client ID** and **Client Secret** it gives you — you'll paste these into Nango next.

### 2. The integration in the Nango dashboard

1. **Integrations** tab → **Add integration** → search for **Google Mail** (provider slug
   `google-mail` — matches `NANGO_INTEGRATION_ID=google-mail` already sitting in `.env`, don't
   rename it).
2. Paste in the Google **Client ID** and **Client Secret** from step 1.
3. Set the scope to `https://www.googleapis.com/auth/gmail.readonly` (same scope as the consent
   screen — they have to match).
4. Save.

### 3. Authorize a connection for the actual Gmail account

1. **Connections** tab → **Add Test Connection** (this is Nango's own hosted OAuth flow — you
   don't need to build any UI for this part).
2. It pops the real Google consent screen — sign in as **nikhilram@gmail.com** (the test user you
   added in step 1) and approve the `gmail.readonly` scope.
3. Nango creates a **Connection ID** for this — copy it into `.env`'s `NANGO_CONNECTION_ID`.

### 4. What the code will actually call (next build step, not done yet)

Nango's `google-mail` integration ships pre-built, so no custom sync/script needs to be written —
just call these through Nango's Actions API using `NANGO_SECRET_KEY` + `NANGO_INTEGRATION_ID` +
`NANGO_CONNECTION_ID`:

- **`list-messages`** — list messages matching a query (e.g. `has:attachment` to skip anything
  without one).
- **`get-message`** — fetch a specific message's metadata/parts.
- **`get-attachment`** — fetch a specific attachment's binary payload by message ID + attachment ID.

The ingest flow: `list-messages(has:attachment)` → for each message, `get-message` to find
attachment parts (images/PDFs) → `get-attachment` per part → decode + write into
`ingest/staging/gmail/`, tagged `source: gmail`, same as the local-folder half. I haven't built
this yet (`ingest/` is still empty) — say the word once the connection is authorized and I'll wire
it up.
