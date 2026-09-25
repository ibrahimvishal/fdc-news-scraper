from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import json
import re
import feedparser

from .http import request_with_retry, USER_AGENT

# hl=en only - no gl/ceid country-edition lock, so results aren't implicitly
# scoped to one country's press.
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en"
BATCH_EXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"

# How far back to accept articles. Filtering is done client-side on each
# entry's published date because Google News RSS's "after:"/"before:"/"when:"
# query operators silently return zero results for these queries — they are
# not a reliable way to scope by date.
LOOKBACK_DAYS = 2

def is_recent(entry) -> bool:
    published = getattr(entry, "published_parsed", None)
    if published is None:
        return False
    published_at = datetime(*published[:6], tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    return published_at >= cutoff

def search(keyword: str) -> list[str]:
    """General Google News search for a keyword - no site restriction. This is
    the catch-all for coverage outside the sites in tags.yaml/search.yaml
    (see app/tags.py), which is now the primary discovery method for the
    known Maldivian outlets."""
    query = f'"{keyword}"'
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    response = request_with_retry("GET", url, headers={"User-Agent": USER_AGENT})
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

def search_all(keywords: list[str]) -> list[str]:
    urls = []
    for keyword in keywords:
        urls.extend(search(keyword))
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
    page = request_with_retry("GET", google_url, headers={"User-Agent": USER_AGENT})
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

    response = request_with_retry(
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
