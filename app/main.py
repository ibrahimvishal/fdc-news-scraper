from datetime import datetime, timezone
from urllib.parse import urlparse

from .config import KEYWORDS, RUN_SUMMARY_ENABLED, RUN_LOG_PATH, POST_REASON_ENABLED
from .database import connect, exists, add
from .search import search, resolve_real_url
from .tags import discover as discover_tag_articles
from .telegram import post_url

def gather_discoveries() -> dict[str, str]:
    """Returns {article_url: reason}. Tag/search-page discovery (app/tags.py) is
    the primary method for the known sites in tags.yaml/search.yaml; the
    general Google News keyword search is the catch-all for everything else.
    If the same URL is found by both, the tag/search-page reason wins (it's
    checked first)."""
    discoveries = {}

    for url, domain in discover_tag_articles().items():
        discoveries.setdefault(url, f"Tag/search page: {domain}")

    for keyword in KEYWORDS:
        for url in search(keyword):
            discoveries.setdefault(url, f"Google News (general): keyword '{keyword}'")

    return discoveries

def build_summary(discovered: int, posted_urls: list[str], skipped: int, failed_urls: list[str]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"FDC News Scraper run finished ({timestamp})",
        f"Discovered={discovered} Posted={len(posted_urls)} "
        f"AlreadySeen={skipped} Failed={len(failed_urls)}",
    ]
    if posted_urls:
        lines.append("Posted:")
        lines.extend(f"  {url}" for url in posted_urls)
    if failed_urls:
        lines.append("Failed:")
        lines.extend(f"  {url}" for url in failed_urls)
    return "\n".join(lines)

def record_summary(summary: str) -> None:
    if not RUN_SUMMARY_ENABLED:
        return

    try:
        post_url(summary)
    except Exception as exc:
        print(f"Failed to post run summary to Telegram: {exc}")

    try:
        RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RUN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(summary + "\n\n")
    except Exception as exc:
        print(f"Failed to write run summary to {RUN_LOG_PATH}: {exc}")

def main():
    print("Starting news search...")
    print(f"Keywords: {len(KEYWORDS)}")

    discoveries = gather_discoveries()
    print(f"Discovered {len(discoveries)} unique URLs.")

    conn = connect()

    posted_urls = []
    failed_urls = []
    skipped = 0

    for url, reason in discoveries.items():
        # Only Google News RSS gives back an obfuscated redirect link that needs
        # server-side resolution; tag/search-page discovery already returns the
        # real publisher URL directly.
        real_url = resolve_real_url(url) if urlparse(url).netloc == "news.google.com" else url

        if exists(conn, real_url):
            skipped += 1
            continue

        message = f"{real_url}\n\n{reason}" if POST_REASON_ENABLED else real_url

        try:
            print(f"Posting: {real_url} ({reason})")
            if post_url(message):
                add(conn, real_url)
                posted_urls.append(real_url)
            else:
                failed_urls.append(real_url)
                print(f"Telegram did not confirm posting: {real_url}")
        except Exception as exc:
            failed_urls.append(real_url)
            print(f"Failed to post {real_url}: {exc}")

    conn.close()

    summary = build_summary(len(discoveries), posted_urls, skipped, failed_urls)
    print(summary)
    record_summary(summary)

if __name__ == "__main__":
    main()
