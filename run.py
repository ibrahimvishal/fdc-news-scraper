import traceback

from app.main import main

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: run failed: {exc}")
        traceback.print_exc()
        try:
            from app.telegram import post_url
            post_url(f"ALERT: FDC News Scraper run failed: {exc}")
        except Exception:
            print("Also failed to send failure alert to Telegram.")
        raise
