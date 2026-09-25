import time
import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

def post_url(url: str) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                API_URL,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": url,
                    "disable_web_page_preview": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return bool(data.get("ok"))
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                print(f"Telegram post failed after {MAX_RETRIES} attempts: {exc}")
                return False
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return False
