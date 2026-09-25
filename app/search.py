from datetime import date, timedelta
from urllib.parse import quote_plus
import feedparser

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

def date_range(days_ago: int):
    target = date.today() - timedelta(days=days_ago)
    next_day = target + timedelta(days=1)
    return target.isoformat(), next_day.isoformat()

def build_query(keyword: str, domain: str | None, days_ago: int) -> str:
    after, before = date_range(days_ago)
    query = f'"{keyword}" after:{after} before:{before}'
    if domain:
        query = f'site:{domain} {query}'
    return query

def search(keyword: str, domain: str | None, days_ago: int) -> list[str]:
    query = build_query(keyword, domain, days_ago)
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    feed = feedparser.parse(url)

    urls = []
    for entry in feed.entries:
        link = getattr(entry, "link", "").strip()
        if link:
            urls.append(link)

    return list(dict.fromkeys(urls))

def search_all(websites: list[str], keywords: list[str]) -> list[str]:
    urls = []

    # Method 1: each keyword restricted to each predefined website.
    for domain in websites:
        for keyword in keywords:
            for days_ago in (0, 1):
                urls.extend(search(keyword, domain, days_ago))

    # Method 2: each keyword against general news search.
    for keyword in keywords:
        for days_ago in (0, 1):
            urls.extend(search(keyword, None, days_ago))

    return list(dict.fromkeys(urls))
