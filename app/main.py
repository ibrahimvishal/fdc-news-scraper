from .config import WEBSITES, KEYWORDS
from .database import connect, exists, add
from .search import search_all
from .telegram import post_url

def main():
    print("Starting news search...")
    print(f"Websites: {len(WEBSITES)}")
    print(f"Keywords: {len(KEYWORDS)}")

    urls = search_all(WEBSITES, KEYWORDS)
    print(f"Discovered {len(urls)} unique URLs.")

    conn = connect()

    posted = 0
    skipped = 0
    failed = 0

    for url in urls:
        if exists(conn, url):
            skipped += 1
            continue

        try:
            print(f"Posting: {url}")
            if post_url(url):
                add(conn, url)
                posted += 1
            else:
                failed += 1
                print(f"Telegram did not confirm posting: {url}")
        except Exception as exc:
            failed += 1
            print(f"Failed to post {url}: {exc}")

    conn.close()

    print(
        f"Finished. Posted={posted}, "
        f"already_seen={skipped}, failed={failed}"
    )

if __name__ == "__main__":
    main()
