from .config import WEBSITES, KEYWORDS
from .database import connect, exists, add
from .search import search_all, resolve_real_url
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

    for google_url in urls:
        real_url = resolve_real_url(google_url)

        if exists(conn, real_url):
            skipped += 1
            continue

        try:
            print(f"Posting: {real_url}")
            if post_url(real_url):
                add(conn, real_url)
                posted += 1
            else:
                failed += 1
                print(f"Telegram did not confirm posting: {real_url}")
        except Exception as exc:
            failed += 1
            print(f"Failed to post {real_url}: {exc}")

    conn.close()

    print(
        f"Finished. Posted={posted}, "
        f"already_seen={skipped}, failed={failed}"
    )

if __name__ == "__main__":
    main()
