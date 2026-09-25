from datetime import datetime, timezone

from .config import WEBSITES, KEYWORDS, RUN_SUMMARY_ENABLED, RUN_LOG_PATH
from .database import connect, exists, add
from .search import search_all, resolve_real_url
from .telegram import post_url

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
    print(f"Websites: {len(WEBSITES)}")
    print(f"Keywords: {len(KEYWORDS)}")

    urls = search_all(WEBSITES, KEYWORDS)
    print(f"Discovered {len(urls)} unique URLs.")

    conn = connect()

    posted_urls = []
    failed_urls = []
    skipped = 0

    for google_url in urls:
        real_url = resolve_real_url(google_url)

        if exists(conn, real_url):
            skipped += 1
            continue

        try:
            print(f"Posting: {real_url}")
            if post_url(real_url):
                add(conn, real_url)
                posted_urls.append(real_url)
            else:
                failed_urls.append(real_url)
                print(f"Telegram did not confirm posting: {real_url}")
        except Exception as exc:
            failed_urls.append(real_url)
            print(f"Failed to post {real_url}: {exc}")

    conn.close()

    summary = build_summary(len(urls), posted_urls, skipped, failed_urls)
    print(summary)
    record_summary(summary)

if __name__ == "__main__":
    main()
