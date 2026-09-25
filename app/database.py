import sqlite3
from .config import DB_PATH

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
    return conn

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
