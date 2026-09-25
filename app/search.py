from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import feedparser

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

# How far back to accept articles. Filtering is done client-side on each
# entry's published date because Google News RSS's "after:"/"before:"/"when:"
# query operators silently return zero results for these queries — they are
# not a reliable way to scope by date.
LOOKBACK_DAYS = 2

def build_query(keyword: str, domain: str | None) -> str:
    query = f'"{keyword}"'
    if domain:
        query = f'site:{domain} {query}'
    return query

def is_recent(entry) -> bool:
    published = getattr(entry, "published_parsed", None)
    if published is None:
        return False
    published_at = datetime(*published[:6], tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    return published_at >= cutoff

def search(keyword: str, domain: str | None) -> list[str]:
    query = build_query(keyword, domain)
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    feed = feedparser.parse(url)

    urls = []
    for entry in feed.entries:
        if not is_recent(entry):
            continue
        link = getattr(entry, "link", "").strip()
        if link:
            urls.append(link)

    return list(dict.fromkeys(urls))

def search_all(websites: list[str], keywords: list[str]) -> list[str]:
    urls = []

    # Method 1: each keyword restricted to each predefined website.
    for domain in websites:
        for keyword in keywords:
            urls.extend(search(keyword, domain))

    # Method 2: each keyword against general news search.
    for keyword in keywords:
        urls.extend(search(keyword, None))

    return list(dict.fromkeys(urls))
