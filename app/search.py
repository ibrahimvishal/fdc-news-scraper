from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import json
import re
import time
import feedparser
import requests

# hl=en only - no gl/ceid country-edition lock, so results aren't implicitly
# scoped to one country's press.
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en"
BATCH_EXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# How far back to accept articles. Filtering is done client-side on each
# entry's published date because Google News RSS's "after:"/"before:"/"when:"
# query operators silently return zero results for these queries — they are
# not a reliable way to scope by date.
LOOKBACK_DAYS = 2

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT = 15

def _request_with_retry(method: str, url: str, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                print(f"Request failed after {MAX_RETRIES} attempts: {url} ({exc})")
                return None
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return None

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
    response = _request_with_retry("GET", url, headers={"User-Agent": USER_AGENT})
    if response is None:
        return []

    feed = feedparser.parse(response.content)

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

    # One request per site per keyword. A combined "(site:a OR site:b OR ...)
    # keyword" query was tried and found to break Google's AND logic between
    # the site clause and the keyword - it returned ~100 generic recent
    # articles per site regardless of keyword relevance, instead of the
    # handful of genuinely on-topic ones. Do not reintroduce that
    # optimization without re-verifying against live results first.
    for domain in websites:
        for keyword in keywords:
            urls.extend(search(keyword, domain))

    # General search, no site restriction.
    for keyword in keywords:
        urls.extend(search(keyword, None))

    return list(dict.fromkeys(urls))

def resolve_real_url(google_url: str) -> str:
    """Decode a Google News redirect link (news.google.com/rss/articles/...) to
    the real publisher URL. These redirect links resolve via client-side JS, so
    fetching them directly (including Telegram's own link-preview fetcher)
    only ever sees a blank "Google News" shell page - not the real article.

    This uses an internal, undocumented Google endpoint. It's best-effort: any
    failure (network, unexpected response shape, missing page metadata) falls
    back to returning the original Google News link rather than dropping the
    article.
    """
    page = _request_with_retry("GET", google_url, headers={"User-Agent": USER_AGENT})
    if page is None:
        return google_url

    id_match = re.search(r'data-n-a-id="([^"]+)"', page.text)
    sg_match = re.search(r'data-n-a-sg="([^"]+)"', page.text)
    ts_match = re.search(r'data-n-a-ts="([^"]+)"', page.text)
    if not (id_match and sg_match and ts_match):
        return google_url

    article_id, sg, ts = id_match.group(1), sg_match.group(1), ts_match.group(1)

    payload_inner = json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        article_id, int(ts), sg,
    ])
    freq = json.dumps([[["Fbv4je", payload_inner, None, "generic"]]])

    response = _request_with_retry(
        "POST", BATCH_EXECUTE_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
        data={"f.req": freq},
    )
    if response is None:
        return google_url

    try:
        text = response.text
        if text.startswith(")]}'"):
            text = text.split("\n", 1)[1]
        data = json.loads(text.lstrip("\n"))
        inner = json.loads(data[0][2])
        real_url = inner[1]
        if isinstance(real_url, str) and real_url.startswith("http"):
            return real_url
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        print(f"Failed to decode redirect for {google_url}: {exc}")

    return google_url
