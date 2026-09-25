from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

with open(BASE_DIR / "config.yaml", "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

WEBSITES = CONFIG.get("websites", [])
KEYWORDS = CONFIG.get("keywords", [])

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DB_PATH = BASE_DIR / "data" / "articles.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Dev/monitoring-stage only: posts a per-run summary (counts, posted/failed URLs) to the
# Telegram channel and appends it to RUN_LOG_PATH. Set to false in .env before wider rollout -
# the channel should only carry actual articles at that point, not operational chatter.
RUN_SUMMARY_ENABLED = os.environ.get("RUN_SUMMARY_ENABLED", "false").strip().lower() == "true"
RUN_LOG_PATH = BASE_DIR / "data" / "run.log"
