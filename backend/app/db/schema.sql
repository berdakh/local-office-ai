PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    UNIQUE(email)
);

CREATE TABLE IF NOT EXISTS correspondence_drafts (
    id          INTEGER PRIMARY KEY,
    recipient   TEXT NOT NULL,
    email       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    template    TEXT NOT NULL,
    notes       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    path        TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- pdf, docx, md, txt, transcript
    meta        TEXT,                     -- json: transcript paths, duration, scripture checks
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    page        INTEGER,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id);

-- Embeddings stored as float32 blobs; searched in Python for now.
-- TODO: move to sqlite-vec once the corpus is large enough to matter.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    dim         INTEGER NOT NULL,
    embedding   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id          INTEGER PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status      TEXT NOT NULL,            -- running, done, error
    inputs      TEXT NOT NULL,            -- json
    outputs     TEXT,                     -- json
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,            -- queued, running, done, error
    progress    REAL NOT NULL DEFAULT 0,
    result      TEXT,                     -- json
    error       TEXT,
    label       TEXT,
    detail      TEXT,
    route       TEXT,
    context     TEXT,                     -- json
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS generated_texts (
    id          INTEGER PRIMARY KEY,
    run_id      TEXT NOT NULL,
    workflow    TEXT NOT NULL,
    output_key  TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    model       TEXT NOT NULL,
    sources     TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (run_id, output_key)
);
CREATE INDEX IF NOT EXISTS generated_texts_date_idx ON generated_texts(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT                      -- json
);
