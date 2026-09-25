# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## Purpose

This project monitors the news for mentions of **FDC (Fahi Dhiriulhun Corporation)** and its
related brand names/projects (Aman Udhares, Aman Dhoadhi, 4000 Flats, Fahi Flats — in both
English and Dhivehi) so that PR/communications staff can react quickly to press coverage.
Twice a day (11:00 AM and 9:00 PM Maldives time) it checks each monitored outlet's own FDC
tag/category page for new articles, plus a general Google News keyword search as a catch-all,
and posts new links to a Telegram group/channel for the team to triage.

This is currently a small, single-purpose VPS script run on a schedule via systemd timer —
not a web app or service. See "Deployment" below for where it actually runs.

## Architecture

```
run.py              entry point → app.main.main(); catches a total run failure and tries to
                     post a Telegram alert before re-raising, so a broken run isn't silent
app/
  config.py         loads .env (Telegram creds, feature flags) and config.yaml (keywords)
  http.py           shared request_with_retry() + USER_AGENT used by search.py and tags.py
  tags.py           scrapes each site's FDC tag/search page (tags.yaml / search.yaml) for
                     article links — the primary discovery method
  search.py         general (no site restriction) Google News RSS keyword search - the
                     catch-all; also resolve_real_url() for Google's redirect links
  database.py       SQLite (data/articles.db) — dedupe store, one table: articles(url, posted_at)
  telegram.py       posts a message to Telegram via sendMessage (with retry/backoff); success ==
                     Telegram confirms "ok"
  main.py           orchestrates: gather_discoveries() -> resolve (Google links only) -> filter
                     already-posted -> post_url() -> record
config.yaml          search keywords only (used by the general Google search)
tags.yaml            FDC tag/category page URL per monitored site — the source of truth for
                      which sites are covered and how
search.yaml           site-search fallback URLs, for sites without a clean tag page
.env                 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, feature flags (not committed)
```

Data flow per run (`app/main.py`'s `gather_discoveries()` + `main()`):
1. **Tag/search-page discovery** (`app/tags.py`, primary method): fetches every URL in
   `tags.yaml` and `search.yaml` (one request each, first page only — no pagination, see
   below) and extracts article links by URL *shape*: a path containing a run of 4+ digits
   (`/85761`, `/news/54293`, `/articles/21805`, ...) or a long hyphenated slug (4+ hyphens,
   30+ chars — for sites like `corporatemaldives.com` that use slugs instead of numeric IDs),
   excluding a small denylist of nav path prefixes (`/category`, `/tag`, `/login`, etc.).
   Verified against all URLs in `tags.yaml`/`search.yaml` at the time this was built — see
   "tag-page extraction heuristic" below before changing it.
2. **General Google News search** (`app/search.py`, catch-all): one query per keyword, no site
   restriction, no country-edition lock (`hl=en` only, no `gl`/`ceid`). Results are filtered
   client-side to the last `LOOKBACK_DAYS` (default 2) using `entry.published_parsed` — see
   "date filtering" below for why this isn't done server-side. Only Google's method needs this;
   tag pages list newest-first, so no date filtering is needed there at all.
3. Both methods' results are merged into one `{url: reason}` dict, tag/search-page results
   first (their reason wins if a URL somehow appears via both methods).
4. Only URLs on `news.google.com` (i.e. from the Google search) go through
   `resolve_real_url()` to decode Google's redirect link to the real publisher URL — tag-page
   URLs are already the real, direct article URL, no resolution needed.
5. For each real URL: check SQLite `exists()` → skip if already posted.
6. Otherwise `post_url()` → only on Telegram API returning `ok: true` is the URL saved via
   `add()`. This "record only after confirmed send" ordering is intentional — it prevents an
   article from being silently marked as "handled" if the Telegram post actually failed.

The DB intentionally stores **only** the resolved real URL + timestamp — no article content/text
is scraped or retained.

## Conventions

- Plain, dependency-light Python (`requests`, `python-dotenv`, `feedparser`, `PyYAML`,
  `beautifulsoup4`). Keep it that way unless there's a concrete reason to add a dependency.
- No test suite currently exists. If you add non-trivial logic (query building, dedup, date
  windows, URL resolution, the tag-page extraction heuristic), prefer adding tests over
  trusting manual runs.
- Adding a monitored site: add its FDC tag/category page URL to `tags.yaml` (or `search.yaml`
  if it doesn't have a clean tag page — see below). Don't hardcode sites in `app/`.
- Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) live only in `.env` (gitignored, `chmod 600`
  on the VPS). Never commit real credentials; `.env.example` documents the required keys with
  placeholder values.
- `app/config.py` reads Telegram env vars eagerly at import time via `os.environ[...]` (not
  `.get`), so a missing `.env` fails fast and loudly on startup rather than later mid-run.
- Network calls go through `app/http.py`'s `request_with_retry()` (`MAX_RETRIES`,
  `RETRY_BACKOFF_SECONDS`). Keep new network calls consistent with that rather than adding bare
  `requests.get`/`.post` calls with no retry handling.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
python run.py
```

## Deployment

Deployed at `/opt/fdc-news-scraper` on a VPS, alongside other unrelated services on that box
(`agreements-sme`, `client-tracker`, `cms-tts` — do not touch those). Connection details
(host, user) aren't kept in this repo — ask the project owner. Scheduled via a systemd oneshot
service + timer (`fdc-news-scraper.service` / `fdc-news-scraper.timer`), not cron — see
README's "Scheduling" section for the unit files and schedule. Git-deployed from this GitHub
repo using a read-only deploy key (`~/.ssh/fdc_news_scraper_deploy` on the VPS); pull latest
with:

```bash
cd /opt/fdc-news-scraper && git pull
```

`.venv/` and `.env` on the VPS are not in git and need to be recreated/updated manually if
dependencies or credentials change (`.venv/bin/pip install -r requirements.txt`, edit `.env`).

## Known limitations / things to keep in mind when extending this

- **Tag-page extraction heuristic can go wrong two ways**: too loose (nav links slip through as
  false "articles") or too strict (a real article gets excluded because its URL doesn't have 4+
  digits or a long-enough hyphenated slug). If a site's tag page stops producing results, or
  starts producing garbage, check `app/tags.py`'s `_looks_like_article()` against that site's
  actual current link structure before assuming the site itself is broken — CMS redesigns will
  break this silently, there's no error, it'll just quietly find 0 (or wrong) articles.
- **URL shape alone isn't enough — some tag pages mix in an unrelated sidebar widget with the
  same shape.** Confirmed live: `javiyani.mv`'s tag page also renders a "trending now" sidebar
  elsewhere on the same page, using the same numeric-ID URL pattern as the genuine tag listing —
  an unrelated Asian Games article got posted to the Telegram channel as a result before this
  was caught. Fixed by clustering candidate links by their nearest classed ancestor's
  (tag name, class set) "template signature" (`_template_signature()`/`_cluster_by_template()`
  in `app/tags.py`) and keeping only the largest cluster, on the assumption that the real
  listing is the dominant one on the page. Similarity is fuzzy (Jaccard ≥
  `TEMPLATE_SIMILARITY_THRESHOLD`, not exact match) because exact matching was tried first and
  was *too* strict — real sites vary a card's classes slightly between instances (e.g. a
  Tailwind spacing utility like `mb-7` present on all-but-the-last item in a row), which falsely
  split one genuine listing into multiple smaller clusters (verified on `avas.mv`: exact
  matching only kept 18 of 25 genuine articles; fuzzy matching recovered 24 of 25). This
  clustering assumption ("largest cluster = real content") could misfire on a page where a
  widget genuinely has more items than the real tag listing - not observed so far, but worth
  knowing if a site's coverage looks suspiciously wrong.
- **Tag pages depend on the publication's own tagging being complete**: if a site's editors
  don't tag an FDC-related article, this method won't find it — this is the tradeoff for the
  much higher precision/recall it gives over keyword search. The general Google search running
  in parallel is the safety net for this, not a redundant afterthought - don't remove it.
- **`sangu.mv`'s site-search URL (in `search.yaml`) returns 403** (likely bot-blocking) even
  though its tag page (in `tags.yaml`) works fine. The search.yaml entry is currently dead
  weight for that domain; harmless (fails gracefully, returns empty) but worth removing if
  confirmed still broken later.
- **`www.oneonline.mv` and `dhen.mv` are blocked from the VPS specifically, not from arbitrary
  machines**: both tag pages work fine fetched from a residential/dev machine, but from the VPS
  return a Cloudflare challenge page (403 "Attention Required!" for oneonline.mv, "Just a
  moment..." for dhen.mv) — a datacenter-IP/ASN-based block, confirmed not fixable by changing
  User-Agent or adding a Referer header. Coverage for these two sites currently relies entirely
  on the general Google search catch-all. Fixing this properly would need a residential/mobile
  proxy for their requests; not implemented, given the complexity/benefit tradeoff. If more
  sites start getting blocked this way, worth revisiting - it may be Cloudflare's default bot
  fight mode rather than something specific to these two, in which case it'll keep recurring as
  more sites are added to `tags.yaml`.
- **`corporatemaldives.com` needs the hyphenated-slug branch of the heuristic**, not the
  digit-run branch — its article URLs are things like
  `/fdc-signs-epc-contract-with-ashoka-buildcon-limited-to-develop-2000-housing-units-in-hulhumale-phase-2/`.
  If a future site also uses slug URLs, verify its typical slug length/hyphen-count against
  `MIN_SLUG_HYPHENS`/`MIN_SLUG_LENGTH` in `app/tags.py` rather than assuming the existing
  thresholds fit.
- **No pagination**: `app/tags.py` only fetches the first page of each tag/search URL. This is
  deliberate — repeat runs plus DB dedup mean the backlog gets caught up over time as long as
  the run cadence keeps up with each site's posting frequency. If a site posts more than a
  page's worth of FDC-tagged articles between two scheduled runs, some could be missed; not
  observed so far, but worth knowing if coverage ever looks like it's skipping things.
- **Google News search remains only for catch-all/safety-net coverage**: don't restore the old
  per-site `site:domain "keyword"` queries — tag pages replaced that method because it's
  fragile (`www.` sensitivity, unreliable date operators, weak Dhivehi recall) and lower
  precision. See git history (commits around the "Switch primary discovery" change) for the
  full reasoning if reconsidering this.
- **Date filtering is client-side, not query-side (Google search only)**: Google News RSS's
  `after:`/`before:`/`when:` query operators were tried and found to silently return **zero
  results** for these queries (confirmed against real, existing FDC coverage) — not "unsupported
  and ignored," but actively filtering everything out. `search.py` fetches each query
  unfiltered and filters on `entry.published_parsed` in Python (`LOOKBACK_DAYS`, default 2).
  Do not reintroduce server-side date operators without re-verifying against live results
  first. This doesn't apply to tag pages, which need no date filtering at all.
- **Google News redirect links require server-side resolution**: `entry.link` from the RSS feed
  is always a `news.google.com/rss/articles/...` link that only resolves via client-side JS — a
  raw fetch (including Telegram's own link-preview fetcher) sees a blank "Google News" page, no
  title/content. `resolve_real_url()` decodes this to the real publisher URL using an internal,
  undocumented Google endpoint (extracts `data-n-a-id`/`-sg`/`-ts` from the redirect page, then
  calls `news.google.com/_/DotsSplashUi/data/batchexecute`). This is inherently fragile — if
  Google changes this mechanism, `resolve_real_url()` falls back to returning the original
  redirect link rather than dropping the article, but the "real URL" behavior would silently
  stop working. Only matters for the general-search path now; tag-page URLs never need this.
- **Dhivehi-script keyword search is weak (Google search only)**: spot-checked against a very
  common Dhivehi word (`ރާއްޖެ`, "Maldives") and got only 1 result via Google News RSS — vs.
  dozens/hundreds expected. This was a major reason for switching to tag-page discovery, which
  relies on each publication's own editorial tagging instead and doesn't have this weakness.
- **No structured logging**: output is `print()` to stdout, captured by systemd/journald
  (`journalctl -u fdc-news-scraper.service`). Retention is handled by journald's own defaults,
  not by the app.
- **No monitoring beyond failure alerts**: `run.py` posts a Telegram alert on an uncaught
  exception, but there's no detection for "the script ran fine but found suspiciously nothing for
  N days" or "the systemd timer silently stopped firing" — those still require an external
  dead-man's-switch (e.g. healthchecks.io) if that level of assurance is needed later.
- **Single Telegram destination**: one bot token/chat ID pair; no per-keyword routing.
- **Dev/monitoring-stage feature flags** (`.env`, both default `false`): `RUN_SUMMARY_ENABLED`
  posts a per-run summary (counts + which URLs) to the channel and appends it to
  `data/run.log`. `POST_REASON_ENABLED` appends a note to each posted article explaining which
  method/site/keyword found it. Both exist to make discovery quality visible during the current
  solo-monitoring period — see project memory `project_soft_launch_monitoring` if available.
  Turn both off before wider team rollout so the channel only carries clean article links.
