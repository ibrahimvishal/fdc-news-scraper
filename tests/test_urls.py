import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "x")

from app.urls import normalize_url, is_related_link  # noqa: E402
from app.database import normalize_existing  # noqa: E402


def test_strips_tracking_params():
    assert normalize_url("https://edition.mv/news/54987?ref=cat-sub") == "https://edition.mv/news/54987"
    assert normalize_url("https://x.com/a/1?utm_source=f&id=5&fbclid=z") == "https://x.com/a/1?id=5"


def test_strips_amp_slash_fragment_and_host_case():
    assert normalize_url("https://www.moneycontrol.com/a-1.html/amp") == "https://www.moneycontrol.com/a-1.html"
    assert normalize_url("https://Site.MV/news/123/#top") == "https://site.mv/news/123"


def test_idempotent():
    u = "https://edition.mv/news/54913?ref=cat-tag-related"
    assert normalize_url(normalize_url(u)) == normalize_url(u)


def test_related_links():
    assert is_related_link("https://edition.mv/news/1?ref=article-related")
    assert is_related_link("https://edition.mv/news/1?ref=cat-tag-related")
    assert not is_related_link("https://edition.mv/news/1?ref=tagpage-latest")
    assert not is_related_link("https://edition.mv/news/1")


def test_migration_collapses_duplicates_keeping_earliest():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE, "
                 "posted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    conn.executemany("INSERT INTO articles (url, posted_at) VALUES (?, ?)", [
        ("https://edition.mv/news/54913?ref=tagpage-latest", "2026-10-01 06:00:00"),
        ("https://edition.mv/news/54913?ref=cat-sub", "2026-10-01 06:00:01"),
        ("https://edition.mv/news/54913", "2026-10-01 06:00:02"),
        ("https://edition.mv/news/54293?ref=tagpage-latest", "2026-09-30 06:00:00"),
    ])
    normalize_existing(conn)
    rows = conn.execute("SELECT url, posted_at FROM articles ORDER BY url").fetchall()
    assert rows == [
        ("https://edition.mv/news/54293", "2026-09-30 06:00:00"),
        ("https://edition.mv/news/54913", "2026-10-01 06:00:00"),
    ]
    assert normalize_existing(conn) == 0
