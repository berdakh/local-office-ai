import sqlite3

from app.db import init_db


def test_migration_adds_meta_column_to_old_database(tmp_path):
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute(
        "CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "path TEXT NOT NULL, kind TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()
    init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    assert "meta" in cols
    init_db(conn)  # idempotent
