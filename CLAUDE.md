# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## Purpose

This project monitors the news for mentions of **FDC (Fahi Dhiriulhun Corporation)** and its
related brand names/projects (Aman Udhares, Aman Dhoadhi, 4000 Flats, Fahi Flats — in both
English and Dhivehi) so that PR/communications staff can react quickly to press coverage.
Twice a day it searches Google News, finds new articles, and posts links to a Telegram
group/channel for the team to triage.

This is currently a small, single-purpose VPS cron script — not a web app or service.

## Architecture

```
run.py              entry point → app.main.main()
app/
  config.py         loads .env (Telegram creds) and config.yaml (websites/keywords) at import time
  search.py         builds Google News RSS queries and parses results via feedparser
  database.py       SQLite (data/articles.db) — dedupe store, one table: articles(url, posted_at)
  telegram.py       posts a URL to Telegram via sendMessage; success == Telegram confirms "ok"
  main.py           orchestrates: search_all() -> filter already-posted -> post_url() -> record
config.yaml          list of monitored websites + search keywords (source of truth for what's tracked)
.env                 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (not committed)
```

Data flow per run (`app/main.py`):
1. `search_all()` runs two discovery methods per keyword: site-restricted (`site:domain`) and
   general news search. Each query is fetched once (no server-side date operator — see note
   below) and results are filtered client-side to the last `LOOKBACK_DAYS` (default 2) using
   each entry's `published_parsed` date.
2. Results are deduplicated in-memory (dict-based, preserves order) before touching the DB.
3. For each URL: check SQLite `exists()` → skip if already posted.
4. Otherwise `post_url()` → only on Telegram API returning `ok: true` is the URL saved via `add()`.
5. This "record only after confirmed send" ordering is intentional — it prevents an article from
   being silently marked as "handled" if the Telegram post actually failed.

The DB intentionally stores **only** URL + timestamp — no article content/text is scraped or
retained.

## Conventions

- Plain, dependency-light Python (`requests`, `python-dotenv`, `feedparser`, `PyYAML`). Keep it
  that way unless there's a concrete reason to add a dependency.
- No test suite currently exists. If you add non-trivial logic (query building, dedup, date
  windows), prefer adding tests over trusting manual runs.
- Config changes (adding a monitored site or keyword) go in `config.yaml`, not hardcoded in `app/`.
- Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) live only in `.env` (gitignored). Never commit
  real credentials; `.env.example` documents the required keys with placeholder values.
- `app/config.py` reads env vars eagerly at import time via `os.environ[...]` (not `.get`), so a
  missing `.env` fails fast and loudly on startup rather than later mid-run.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
python run.py
```

## Known limitations / things to keep in mind when extending this

- **Single search backend**: everything goes through Google News RSS (`feedparser`). It's free
  and dependency-light but unofficial — no SLA, results can be rate-limited or change format
  without notice.
- **Date filtering is client-side, not query-side**: Google News RSS's `after:`/`before:`/`when:`
  query operators were tried and found to silently return **zero results** for these queries
  (confirmed against real, existing FDC coverage) — not "unsupported and ignored," but
  actively filtering everything out. `search.py` now fetches each query unfiltered and filters
  on `entry.published_parsed` in Python (`LOOKBACK_DAYS`, default 2). Do not reintroduce
  server-side date operators without re-verifying against live results first.
- **No retry/backoff**: a single failed request (network blip, Google rate limit) just drops that
  keyword/site combination for the run; it isn't retried until the next scheduled run.
- **No structured logging**: output is `print()` to stdout, redirected to a log file by cron.
  There's no log rotation configured in the README's cron example.
- **No monitoring/alerting**: if the script silently stops finding results (e.g. Google changes
  RSS behavior, or the VPS cron stops firing), nothing currently notifies anyone.
- **Single Telegram destination**: one bot token/chat ID pair; no per-keyword routing.
- **Query volume**: for N websites × M keywords, plus M keywords for general search, each run
  issues `N*M + M` RSS requests sequentially — worth watching as `config.yaml` grows, both for
  runtime and for Google rate-limiting risk.
