"""Stage 6 API — read-only search + natural-language Q&A over stored documents.

`/api/ask` does NOT use embeddings or a vector DB (out of scope per CLAUDE.md) — it strips
stopwords from the question, runs the remaining terms through the existing FTS5 index (OR'd
together, ranked by bm25 relevance), then hands the top matches to a local Ollama text model
(`qwen2.5:7b`) to synthesize a short answer. This keeps the whole path local/offline (no Respan,
no Lambda) so it works under the "network-off demo" constraint.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
from store import get_conn, search  # noqa: E402
from gmail import sync_gmail  # noqa: E402

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
ASK_MODEL = os.environ.get("ASK_MODEL", "qwen2.5:7b")
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "retrace.db"))

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
    "at", "for", "with", "and", "or", "but", "if", "then", "so", "do", "does", "did", "can",
    "could", "will", "would", "should", "may", "might", "must", "shall", "i", "you", "he", "she",
    "it", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "its", "our",
    "their", "this", "that", "these", "those", "what", "when", "where", "who", "whom", "which",
    "why", "how", "give", "tell", "please", "me", "about", "get", "know", "let", "us",
    # generic accounting/question words that show up as literal text on nearly every receipt
    # (e.g. "TOTAL: $X") — leaving these in over-broadens the OR query and pulls in unrelated
    # documents, which previously produced a wrong aggregate (summed unrelated receipts).
    "total", "totals", "summary", "spent", "spend", "amount", "amounts", "much", "many",
    "number", "numbers", "sum", "cost", "costs", "paid", "pay", "money",
}

app = FastAPI(title="Retrace")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"], "doc_type": row["doc_type"], "title": row["title"], "date": row["date"],
        "amount": row["amount"], "currency": row["currency"], "entity": row["entity"],
        "identifiers": json.loads(row["identifiers"] or "[]"),
        "key_values": json.loads(row["key_values"] or "{}"),
        "summary": row["summary"], "agreement": row["agreement"], "source": row["source"],
        "file_path": row["file_path"],
    }


def _keywords(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _fts_query(keywords: list[str]) -> str:
    return " OR ".join(f'"{k}"' for k in keywords)


def _call_local_llm(question: str, matches: list[dict]) -> str:
    receipt_total = sum(
        m["amount"] for m in matches if m.get("doc_type") == "receipt" and m.get("amount") is not None
    )
    prompt = f"""You are answering a question about the user's own stored personal documents \
(receipts, cards/IDs, forms/letters, screenshots). Only use the information in CONTEXT below — \
never invent a value. If the answer genuinely isn't in the context, say plainly it wasn't found \
in the indexed documents.

Question: {question}

Context (matched documents, most relevant first):
{json.dumps(matches, indent=2)}

Precomputed total amount across matched receipts, if useful for a "how much did I spend"-style \
question: {receipt_total}

Answer in 1-3 concise sentences. Cite specific values (amounts, dates, names, identifiers) from \
the context verbatim rather than paraphrasing numbers.
"""
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": ASK_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


class AskRequest(BaseModel):
    question: str


@app.get("/api/search")
def api_search(q: str):
    conn = get_conn(DB_PATH)
    rows = search(conn, q)
    return {"query": q, "results": [_row_to_dict(r) for r in rows]}


@app.post("/api/ask")
def api_ask(req: AskRequest):
    conn = get_conn(DB_PATH)
    keywords = _keywords(req.question)
    if not keywords:
        return {"question": req.question, "answer": "Ask something a bit more specific.", "sources": []}

    fts_query = _fts_query(keywords)
    rows = search(conn, fts_query)
    matches = [_row_to_dict(r) for r in rows[:8]]

    if not matches:
        return {
            "question": req.question,
            "answer": "Nothing in the indexed documents matches that.",
            "sources": [],
        }

    answer = _call_local_llm(req.question, matches)
    return {"question": req.question, "answer": answer, "sources": matches}


@app.post("/api/sync/gmail")
def api_sync_gmail():
    return sync_gmail()


web_dir = Path(__file__).parent.parent / "web"
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
