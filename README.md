# DealFinder — retro games deal finder & reseller system

A one-person reselling machine: it watches UK marketplaces for under-priced retro games and consoles, works out
what each listing is really worth and what it would net after every fee, pings your phone about the good ones, and
then runs the stock from "bought" to "sold" with honest listings and a P&L that shows whether the model was right.

**It never buys, bids or messages anyone. You make every purchase.** It only alerts.

The system is niche-agnostic: "retro games" is a config file (`app/niches/retro_games.yaml`). A second niche is a
second YAML file (or the Niches page), not a rewrite.

## How it works (plain English)

Think of it as a production line with six stations:

1. **Sourcing (watchers).** Every few minutes a job polls each enabled source for your search terms.
   eBay goes through the official Browse API (OAuth). Facebook Marketplace, Vinted, Gumtree, Shpock and Depop go
   through a *browser helper*: a real Chromium window logged in as you, that reads search pages at a human pace
   (45–120 s between pages, a cap per hour, quiet hours). If a site shows a CAPTCHA or login wall, that source
   pauses and you get a push: "Vinted needs you to log in / check the browser". Duplicates (same listing seen
   twice, or the same item cross-posted on two sites) are dropped.
2. **Identification & valuation.** Each new listing is turned into a structured item (platform, title, region,
   completeness, bundle contents, accessories) by Claude — or a rule-based mock when no API key is set — and
   checked for risk flags (repro carts, "untested", stock photos, stolen-goods wording, prices too good to be
   true). Then it is priced from sold comparables: your CSV uploads (Terapeak), your own past sales (weighted more
   as they grow), eBay's Marketplace Insights API once you have access, and a mock set for demos. Output: median,
   interquartile range, how many sold, how many are active, sell-through, estimated days to sell, confidence.
3. **Profit engine.** Full landed P&L: price + buyer-protection fees + inbound postage (or the fuel/time cost of
   collecting it from wherever you currently are) versus expected sale price − selling fees − outbound postage −
   packaging − a returns reserve. Then the tiered rules (fast sellers need 25%, slower ones more), the phase mode
   (Capital Growth ignores slow stock unless it's a 50%+ win), the £8 profit floor, low-confidence handling, a cash
   reserve check, and a 0–100 score.
4. **Push notifications.** ntfy (free, self-hostable) or Pushover. Hot deals push immediately with sound; the
   rest are batched into a digest every 30 minutes; a summary arrives at 8am.
5. **Inventory & listing.** Tap *Bought* and the deal becomes stock with a SKU and a printable label. Work it
   through testing (a per-niche checklist), listing (generated SEO title ≤ 80 chars, honest condition copy, item
   specifics, suggested price with an auto-markdown schedule, photo shot list), publishing to eBay via the Sell
   APIs, cross-listing CSV export, and recording the sale with the real fees. When it sells on one platform the
   others are flagged for removal (eBay is ended automatically).
6. **Dashboard & analytics.** Mobile-first web app: home, deals feed, kanban stock board with ageing highlights,
   P&L per item/month/source/platform with predicted-vs-actual, capital projections (worst/expected/best),
   weekly AI growth tips with the "ready to clone into a second niche" rule, settings, niches, health.

## Run it

### One command (Docker)

```bash
cp .env.example .env          # optional; defaults run in mock mode
docker compose up --build
```

Open http://localhost:8000. Postgres, a self-hosted ntfy server (port 8080) and the app start together. With
`MOCK_MODE=true` (the default) it loads 50 realistic seed listings, prices them, alerts (to the log), and creates a
little demo stock history so every page has data.

### Local (SQLite, no Docker)

```bash
make install     # pip deps + Chromium for the browser helper
make run         # alembic upgrade + uvicorn on :8000
make test        # 79 tests, offline
```

### Going live

Follow `SETUP_CHECKLIST.md` — it is the complete list of things only you can do (keys, logins, fee checks).
Set `MOCK_MODE=false` once the keys are in `.env`.

## Project layout

```
app/
  config.py            settings from .env            app/models.py        all tables
  niches/              niche YAML configs + loader   app/settings_store.py defaults for settings, fees, postage
  sourcing/            SourceWatcher interface, eBay Browse API, browser helper (+ selectors/*.yaml), dedupe, runner
  identification/      Claude client (+mock), normaliser, risk flags, valuation + SoldDataProviders
  profit/              distance, profit engine, tiered rules & scoring
  notify/              Notifier interface, ntfy, Pushover, mock, alert service (digest, daily summary)
  inventory/           SKU, labels (PDF), testing checklists, listing generator, eBay Sell API (+mock), cross-lister, lifecycle
  analytics/           P&L, projections, weekly insights
  web/                 FastAPI routes + Jinja/Tailwind/HTMX templates
  jobs/scheduler.py    APScheduler jobs (one per source, digest, daily, weekly insights, purge, eBay sales sync)
  pipeline.py          listing -> item -> valuation -> P&L -> rules -> alert
  seed.py              50 seed listings, mock sold comps, demo history
prompts/               versioned Claude prompts (normalise, risk_flags, listing_copy, insights)
alembic/               migrations          tests/   unit, parser-fixture, e2e and web tests
scripts/helper_login.py  open the helper browser so you can log in once
```

## Safety & compliance (built in, not optional)

- No automatic buying, bidding, offers or messages — the code has no such calls.
- eBay only via official APIs (Browse, Marketplace Insights, Sell). No scraping of eBay anywhere.
- Browser helper: your own logged-in session, human pacing, pause-on-block, no CAPTCHA solving, no proxies, no
  fingerprint spoofing. It only loads search and listing pages.
- Secrets only in `.env`; the log formatter redacts anything that looks like a key or token.
- Seller names/locations are stripped from listings you passed on after 90 days (`PASSED_DEAL_RETENTION_DAYS`).
- The listing generator describes faults plainly and labels reproductions as reproductions.

See `DECISIONS.md` for every assumption, `RUNBOOK.md` for operations, `SETUP_CHECKLIST.md` for what you must do by hand.
