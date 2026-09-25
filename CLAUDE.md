# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## Purpose

This project monitors the news for mentions of **FDC (Fahi Dhiriulhun Corporation)** and its
related brand names/projects (Aman Udhares, Aman Dhoadhi, 4000 Flats, Fahi Flats — in both
English and Dhivehi) so that PR/communications staff can react quickly to press coverage.
Twice a day (11:00 AM and 9:00 PM Maldives time) it searches Google News, finds new articles,
and posts links to a Telegram group/channel for the team to triage.

This is currently a small, single-purpose VPS cron script — not a web app or service.

## Architecture

```
run.py              entry point → app.main.main(); catches a total run failure and tries to
                     post a Telegram alert before re-raising, so a broken run isn't silent
app/
  config.py         loads .env (Telegram creds) and config.yaml (websites/keywords) at import time
  search.py         builds Google News RSS queries, filters by date client-side, resolves
                     Google's redirect links to real publisher URLs
  database.py       SQLite (data/articles.db) — dedupe store, one table: articles(url, posted_at)
  telegram.py       posts a URL to Telegram via sendMessage (with retry/backoff); success ==
                     Telegram confirms "ok"
  main.py           orchestrates: search_all() -> resolve_real_url() -> filter already-posted
                     -> post_url() -> record
config.yaml          list of monitored websites + search keywords (source of truth for what's
                      tracked). Domain form matters — see "site: matching" below; don't assume
                      bare-domain is always right without checking.
.env                 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (not committed)
```

Data flow per run (`app/main.py`):
1. `search_all()` runs two discovery methods, both against Google News RSS with no
   country-edition lock (`hl=en` only, no `gl`/`ceid`):
   - **Site-restricted**: one `site:domain "keyword"` query per website per keyword. A combined
     `(site:a OR site:b OR ...) "keyword"` query was tried to cut request volume and found to
     break Google's AND logic between the site clause and the keyword — it returned ~100
     generic recent articles per site regardless of keyword relevance (confirmed live: one
     slipped through to the Telegram channel) instead of the handful of genuinely on-topic
     ones. Do not reintroduce that without re-verifying against live results first.
   - **General**: each keyword with no site restriction, one request per keyword.
2. Each query's results are filtered client-side to the last `LOOKBACK_DAYS` (default 2) using
   `entry.published_parsed` — see "date filtering" below for why this isn't done server-side.
3. Results are deduplicated in-memory (dict-based, preserves order).
4. Each surviving URL — still a `news.google.com/rss/articles/...` redirect link at this point —
   is resolved to the real publisher URL via `resolve_real_url()` before anything else touches it.
5. For each real URL: check SQLite `exists()` → skip if already posted.
6. Otherwise `post_url()` → only on Telegram API returning `ok: true` is the URL saved via `add()`.
   This "record only after confirmed send" ordering is intentional — it prevents an article from
   being silently marked as "handled" if the Telegram post actually failed.

The DB intentionally stores **only** the resolved real URL + timestamp — no article content/text
is scraped or retained.

## Conventions

- Plain, dependency-light Python (`requests`, `python-dotenv`, `feedparser`, `PyYAML`). Keep it
  that way unless there's a concrete reason to add a dependency.
- No test suite currently exists. If you add non-trivial logic (query building, dedup, date
  windows, URL resolution), prefer adding tests over trusting manual runs.
- Config changes (adding a monitored site or keyword) go in `config.yaml`, not hardcoded in `app/`.
- Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) live only in `.env` (gitignored, `chmod 600`
  on the VPS). Never commit real credentials; `.env.example` documents the required keys with
  placeholder values.
- `app/config.py` reads env vars eagerly at import time via `os.environ[...]` (not `.get`), so a
  missing `.env` fails fast and loudly on startup rather than later mid-run.
- Network calls in `search.py` and `telegram.py` go through a small retry-with-backoff wrapper
  (`MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`). Keep new network calls consistent with that rather
  than adding bare `requests.get`/`.post` calls with no retry handling.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
python run.py
```

## Deployment

Deployed at `/opt/fdc-news-scraper` on the Leaseweb VPS (`vishal@23.111.14.67`), alongside
other unrelated services on that box (`agreements-sme`, `client-tracker`, `cms-tts` — do not
touch those). Scheduled via a systemd oneshot service + timer (`fdc-news-scraper.service` /
`fdc-news-scraper.timer`), not cron — see README's "Scheduling" section for the unit files and
schedule. Git-deployed from this GitHub repo using a read-only deploy key
(`~/.ssh/fdc_news_scraper_deploy` on the VPS); pull latest with:

```bash
cd /opt/fdc-news-scraper && git pull
```

`.venv/` and `.env` on the VPS are not in git and need to be recreated/updated manually if
dependencies or credentials change (`.venv/bin/pip install -r requirements.txt`, edit `.env`).

## Known limitations / things to keep in mind when extending this

- **Single search backend**: everything goes through Google News RSS (`feedparser`). It's free
  and dependency-light but unofficial — no SLA, results can be rate-limited or change format
  without notice. This is a deliberate scope choice (confirmed with the project owner) over
  adding a paid general web-search API; it means only content Google categorizes as "News" is
  found — not blog posts, forum threads, or social media mentions.
- **Date filtering is client-side, not query-side**: Google News RSS's `after:`/`before:`/`when:`
  query operators were tried and found to silently return **zero results** for these queries
  (confirmed against real, existing FDC coverage) — not "unsupported and ignored," but actively
  filtering everything out. `search.py` fetches each query unfiltered and filters on
  `entry.published_parsed` in Python (`LOOKBACK_DAYS`, default 2). Do not reintroduce
  server-side date operators without re-verifying against live results first.
- **Google News redirect links require server-side resolution**: `entry.link` from the RSS feed
  is always a `news.google.com/rss/articles/...` link that only resolves via client-side JS — a
  raw fetch (including Telegram's own link-preview fetcher) sees a blank "Google News" page, no
  title/content. `resolve_real_url()` decodes this to the real publisher URL using an internal,
  undocumented Google endpoint (extracts `data-n-a-id`/`-sg`/`-ts` from the redirect page, then
  calls `news.google.com/_/DotsSplashUi/data/batchexecute`). This is inherently fragile — if
  Google changes this mechanism, `resolve_real_url()` falls back to returning the original
  redirect link rather than dropping the article, but the "real URL" behavior would silently stop
  working. If posted messages start looking like bare `news.google.com` links again, this is the
  first place to check.
- **`site:` matching is `www.`-sensitive and inconsistent per-site**: Google's `site:` operator
  frequently fails to match a domain's canonical form if `config.yaml` lists it differently
  (mostly `www.` vs bare — verified: 14 of the original 17 configured sites returned near-zero
  results with `www.` where the bare domain returned dozens to 100). This isn't uniform — one
  site (`www.oneonline.mv`) actually performs *better* with `www.`, and one (`www.sangu.tv`)
  returns zero either way and may not be indexed by Google News at all. When adding a new site to
  `config.yaml`, spot-check both forms with a generic query (`site:<domain> news`) before assuming
  the bare domain is correct.
- **Dhivehi-script keyword search is weak**: spot-checked against a very common Dhivehi word
  (`ރާއްޖެ`, "Maldives") and got only 1 result via Google News RSS — vs. dozens/hundreds expected.
  Google News RSS appears to have poor recall for Thaana-script queries generally, not just niche
  FDC terms. The Dhivehi keywords in `config.yaml` are kept as an additional signal, but the
  English keywords are the more reliable coverage; don't assume parity between the two halves of
  the keyword list.
- **No structured logging**: output is `print()` to stdout, redirected to a log file by cron.
  Log rotation is handled at the OS level (logrotate), not in the app — see README.
- **No monitoring beyond failure alerts**: `run.py` posts a Telegram alert on an uncaught
  exception, but there's no detection for "the script ran fine but found suspiciously nothing for
  N days" or "cron silently stopped firing" — those still require an external dead-man's-switch
  (e.g. healthchecks.io) if that level of assurance is needed later.
- **Single Telegram destination**: one bot token/chat ID pair; no per-keyword routing.
- **Query volume**: `N websites × M keywords + M keywords` — ~180 requests/run for the current
  17 sites × 10 keywords, down from ~360 in the original per-site-per-day implementation (the
  date-based `days_ago` loop was removed; see date filtering above). Sequential with
  retry/backoff. This is a deliberate correctness-over-speed tradeoff — see the OR-combined
  query note above for why it isn't smaller.
