import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def post_url(url: str) -> bool:
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
