-- One row per document found. Columns mirror the data model in ../CLAUDE.md exactly —
-- do not add columns here without updating that schema first.
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    -- produced by the extraction model (stage 4), null rather than guessed
    doc_type      TEXT,       -- 'receipt' | 'card' | 'form' | 'screenshot_text'
    title         TEXT,
    date          TEXT,       -- ISO date, null if absent
    amount        REAL,       -- receipts only
    currency      TEXT,
    entity        TEXT,       -- merchant, issuer, sender
    identifiers   TEXT,       -- JSON array, e.g. ["policy #A4471-B"]
    key_values    TEXT,       -- JSON object, e.g. {"expires": "2029-03"}
    summary       TEXT,

    -- added by the pipeline, not the model
    source        TEXT NOT NULL,   -- 'photos' | 'gmail'
    file_path     TEXT NOT NULL,
    taken_at      TEXT,
    ocr_text      TEXT,
    agreement     TEXT,            -- 'high' | 'flagged', null until stage 5 runs

    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Full-text search over extracted fields + OCR text. No vector DB, no embeddings.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    entity,
    summary,
    identifiers,
    key_values,
    ocr_text,
    content='documents',
    content_rowid='id'
);

-- Keep the FTS index in sync with the base table.
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, entity, summary, identifiers, key_values, ocr_text)
    VALUES (new.id, new.title, new.entity, new.summary, new.identifiers, new.key_values, new.ocr_text);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, entity, summary, identifiers, key_values, ocr_text)
    VALUES ('delete', old.id, old.title, old.entity, old.summary, old.identifiers, old.key_values, old.ocr_text);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, entity, summary, identifiers, key_values, ocr_text)
    VALUES ('delete', old.id, old.title, old.entity, old.summary, old.identifiers, old.key_values, old.ocr_text);
    INSERT INTO documents_fts(rowid, title, entity, summary, identifiers, key_values, ocr_text)
    VALUES (new.id, new.title, new.entity, new.summary, new.identifiers, new.key_values, new.ocr_text);
END;
