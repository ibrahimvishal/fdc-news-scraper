import time
import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT = 15

def request_with_retry(method: str, url: str, **kwargs):
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
