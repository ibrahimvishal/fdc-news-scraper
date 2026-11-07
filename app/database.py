import sqlite3
from .config import DB_PATH
from .urls import normalize_url

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            posted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    normalize_existing(conn)
    return conn

def normalize_existing(conn) -> int:
    """One-time-ish migration (idempotent): rewrite stored URLs to their
    normalized form, collapsing rows that differed only by tracking params or
    /amp. Without this, old rows like '...?ref=tagpage-latest' would no longer
    match the normalized URL and the article would be re-posted. Keeps the
    earliest posted_at. Returns the number of rows changed or removed."""
    rows = conn.execute("SELECT id, url FROM articles ORDER BY posted_at, id").fetchall()
    seen = set()
    to_delete, to_update = [], []
    for row_id, url in rows:
        norm = normalize_url(url)
        if norm in seen:
            to_delete.append(row_id)
        else:
            seen.add(norm)
            if norm != url:
                to_update.append((norm, row_id))
    # Delete first: a survivor's normalized URL may equal a duplicate's
    # current URL, which would violate the UNIQUE constraint on update.
    conn.executemany("DELETE FROM articles WHERE id = ?", [(i,) for i in to_delete])
    conn.executemany("UPDATE articles SET url = ? WHERE id = ?", to_update)
    changed = len(to_delete) + len(to_update)
    conn.commit()
    return changed

def exists(conn, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,)
    ).fetchone()
    return row is not None

def add(conn, url: str):
    conn.execute(
        "INSERT OR IGNORE INTO articles (url) VALUES (?)", (url,)
    )
    conn.commit()
