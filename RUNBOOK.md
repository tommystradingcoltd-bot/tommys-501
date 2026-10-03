# Runbook

## Daily
- Phone: act on pushes (Bought / Pass / Watch on the deal page). Digest arrives every 30 min, summary at 8am.
- Home page: tasks (urgent "remove from other platforms"), sources needing attention, ageing stock.

## When a browser source breaks (selectors)
Symptoms: Health shows the source `error` with "navigation failed" or it runs fine but finds 0 listings.

1. Open the site in the helper browser to see what changed: `BROWSER_HEADLESS=false make run`, or run
   `python -m scripts.helper_login vinted` and browse by hand.
2. Edit `app/sourcing/browser/selectors/<site>.yaml` only:
   - `results.item` – the container of one search result; `results.link`, `title`, `price`, `image`, `location`.
   - `detail.*` – fields on the listing page.
   - `block_signals` – selectors/text that mean CAPTCHA, login wall or block.
   - `search_url` – the search URL template (`{query}`, `{max_price}`, `{location_slug}`).
   Several comma-separated selectors are tried in order; `text=...` entries match page text.
3. Save a copy of the real page as `tests/fixtures/html/<site>_search.html` (scrub personal data) and run
   `pytest tests/test_parsers.py` — it must find ≥ 2 listings with title, price and URL.
4. Restart the app (selectors load at startup) and press "Run now" on the Health page.

## When a source says "needs you to log in" / CAPTCHA / blocked
1. Run `python -m scripts.helper_login <site>` on the machine running the watchers, log in or solve the CAPTCHA by hand.
2. Health page → "I've fixed it – resume". The source only resumes when you say so.
3. Blocked repeatedly? Lower `max_page_loads_per_hour`, raise the delays, widen quiet hours (Settings → Sources). Do not add proxies.

## eBay API problems
- `eBay OAuth failed: HTTP 401` – wrong keyset or sandbox/production mismatch (`EBAY_ENV`).
- `HTTP 429` – rate limited; the client backs off automatically. Reduce `poll_interval_min` frequency for eBay.
- Marketplace Insights returns nothing – access not granted yet; keep uploading Terapeak CSVs.

## Adding a niche
Option A (dashboard): Niches → create with slug, name and search terms → open it → edit the YAML (platform aliases,
normalisation hints, risk keywords, testing checklist, postage classes, photo shot list) → Save. Sources start
using the new search terms on their next run.

Option B (file): copy `app/niches/retro_games.yaml` to `app/niches/<slug>.yaml`, edit, restart. The loader creates
the niche and its search queries if the slug is new (it never overwrites a config edited in the dashboard).

The profit engine, rules, notifications, inventory and analytics are niche-agnostic; the Claude prompts take the
niche's hints. Sold comps are per niche — upload a CSV for the new niche.

## Changing fees, postage, rules
All in Settings. Each fee/postage row has a "last verified" date; untick nothing — just tick "verified today" when
you've checked it. Changes apply to the next listing scored (existing deals keep their numbers).

## Database
- Migrations: edit `app/models.py` → `make migrate m="describe change"` → commit `alembic/versions/*`.
- Backup: `make backup` (Postgres dump via compose, or SQLite file copy) into `backups/`.
- Restore (Postgres): `docker compose up -d db && make restore f=backups/dealfinder-YYYY-MM-DD.sql`.
- Restore (SQLite): stop the app, copy the backup to `data/dealfinder.db`.
- Also back up `data/browser_profile/` (your marketplace logins) and `.env`.

## Logs & health
- `/healthz` returns JSON per source (for uptime monitors). `/health` is the human page with jobs and recent pushes.
- Docker: `docker compose logs -f app`. Credentials are redacted in logs.

## Resetting the demo data
Stop the app, delete `data/dealfinder.db` (or `docker compose down -v` for Postgres), start again with `MOCK_MODE=true`.

## Going from mock to live, safely
1. Keys in `.env`, `MOCK_MODE=false`, restart; check Health: eBay `ok`.
2. Watch the Deals feed for a day with "include non-alerts" to sanity-check valuations before trusting alerts.
3. Upload Terapeak CSVs for your main platforms (confidence goes from low to high at 15 comps).
4. Enable browser sources one at a time after logging in; watch Health for a day.
