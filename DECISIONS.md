# Decisions & assumptions

One line each. "Spec" = the build prompt.

## Stack
- Python 3.11-compatible code (the dev container has 3.11; the Docker image is Playwright's Python image). Spec said 3.12; nothing 3.12-only is used.
- FastAPI + Jinja2 + HTMX + Tailwind (CDN) instead of Next.js: one process, one container, far simpler for a solo phone-first user; spec allowed it.
- APScheduler (in-process, single worker thread) instead of Celery+Redis: fewer moving parts; the single worker also keeps the browser helper strictly sequential.
- SQLite by default locally, Postgres in docker compose. Alembic migration `fc9200b125eb` is the initial schema; `create_all` also runs at startup so a fresh SQLite works without alembic.
- No CSS framework: one hand-written stylesheet (`app/web/static/app.css`) in a Revolut-style idiom (balance hero, bottom tab bar on phones / sidebar on desktop, transaction-style rows, chip filters, automatic dark mode). No CDN dependency, so it looks the same offline.
- Claude model default `claude-opus-5-5` (configurable via `CLAUDE_MODEL`). Prompts are plain Markdown files in `/prompts` with `{{var}}` placeholders and a version suffix.
- The Claude client asks for a single JSON object and parses it tolerantly rather than using structured-output features, to stay robust across SDK versions.

## Sourcing
- eBay Browse API search runs two queries per term: Buy It Now newest-first and auctions ending soonest, merged by item id.
- Browser sources are **disabled by default** and only start when `BROWSER_SOURCES_ENABLED=true`; in `MOCK_MODE` they read the fixture HTML pages so the whole pipeline runs offline.
- Facebook Marketplace and Gumtree listings are treated as collection-only unless the text says it can be posted; Vinted and Depop are always posted; Shpock is either.
- Block/login/CAPTCHA detection is selector- and text-based per site (`block_signals` in the selector YAML). On detection the source status becomes `needs_login` / `paused` / `blocked`, one push is sent (de-duplicated for 6 h), and it stays paused until you press "resume" on the Health page.
- Hourly page-load budget and the randomised delay live in `RateLimiter`; quiet hours are checked per page load. Exhausting the budget pauses the source until the next poll.
- Cross-post duplicates: fuzzy title ≥ 90 and price within 5%, or perceptual-hash distance ≤ 6 with title ≥ 70. Image hashes are only computed when an image is downloaded (not in the mock), so title+price is the main signal today.
- The paid-data provider is a stub class (`PaidFeedWatcher`) wired into the registry and the sources table (disabled).

## Identification & valuation
- The mock normaliser is rule-based (platform aliases from the niche config, completeness/region regexes, a title alias table, bundle detection). It is good enough for the seed data and tests; Claude replaces it when a key is present.
- Consoles only have completeness `loose` or `boxed`.
- Item cache key = sha1(niche|platform|title|region|completeness); valuations cache for 24 h (`valuation_cache_hours`).
- Comps window 90 days (`comp_window_days`). Title match = rapidfuzz token_set_ratio ≥ 85 within the same platform; region/completeness must match when known.
- If no comps exist for the exact completeness, comps of any completeness are used with multipliers (loose 0.6, boxed 0.85, cib 1.0, sealed 2.0, graded 3.0) at half weight.
- Days-to-sell model: a new listing competes with `active` listings at `sold/90` sales per day; estimate = active ÷ sales-per-day × 0.4, clamped 3–365. Documented as a heuristic to be calibrated from your own sales.
- Confidence: low < 5 comps, medium 5–14, high ≥ 15 (downgraded to medium if the IQR is > 60% of the median).
- Own sales weight = 1 + 0.25 × matches (max 3×).
- Active-listing count comes from the Browse API `total` (mock: the seed table).
- Bundles are valued as the sum of identified parts; unidentified "7 sports titles" are worth £0 (conservative). Days to sell = average of parts.
- Marketplace Insights provider is implemented against the documented endpoint but returns nothing until `EBAY_MARKETPLACE_INSIGHTS_ENABLED=true` and real keys exist.

## Profit engine & rules
- Selling platform for the forecast is always eBay (fees from `fee_config`); payment processing is treated as included in eBay's FVF (managed payments), PayPal fees are only applied for non-eBay platforms.
- Unknown inbound postage is assumed equal to the outbound rate for the item's weight class.
- Collection cost = round-trip miles × pence/mile + (round-trip hours at `avg_speed_mph` + `handling_minutes`) × hourly rate. Distances use postcode-area centroids (~120 areas) and a town table with a 1.25 road factor: approximate by design.
- Collections beyond `collection_max_miles` (default 40) are not alerted unless the margin is ≥ 60%, then they're "check manually".
- Bundles bought to split: outbound postage, packaging and the fixed per-order fee are multiplied by the number of identified items.
- Score = 100 × min(margin/0.6, 1) × speed (1 − days/90, floor 0.1) × confidence (high 1 / medium 0.8 / low 0.5) × magnitude (0.6 + profit/100, cap 1). High priority at score ≥ 70.
- Large-deal relief is 5 margin points for buy price > £150 (both configurable).
- Phase mode Capital Growth: tiers beyond 30 days alert only at ≥ 50% margin (`steady_min_margin_override`).
- Hard-block risk codes (`repro`, `too_good`, `stolen_signals`) never alert regardless of margin; other high-severity flags alert only at ≥ 60% margin and are labelled "check manually".
- Capital check uses the ledger balance (starting capital − purchases + net sale proceeds) against `capital_reserve` (£300).

## Notifications
- ntfy priorities: high → 5 (sound), default → 3, low → 2. Click opens the dashboard deal page; actions link to the listing and the deal.
- High-priority alerts send immediately except in notify quiet hours (22–07); everything else waits for the 30-minute digest. Daily summary at 08:00 Europe/London.
- Source-status, urgent-task (remove from other platforms) and test notifications use the same channel.

## Inventory & listing
- SKU format `<NICHE3>-<PLATFORM5>-<YYMM>-<SEQ4>`, e.g. `RG-SNES-2610-0042`; labels are 62×29 mm PDFs with a Code128 barcode.
- Status flow: in_transit → testing → ready_to_photograph → listed → sold → shipped (→ returned). Collection purchases start at `testing`.
- Suggested price = median × (1 + uplift) × 1.04, rounded to £x.99 above £20; auto-markdown at 100/150/200% of expected days (−5/−10/−15%).
- When an item sells elsewhere, eBay offers are withdrawn through the API automatically; other platforms get an urgent task + push.
- The cross-lister CSV is a generic, column-stable format (sku, title, description, price, condition, category, brand, platform, …) rather than one vendor's exact template; `CrossLister` is an interface with a no-op implementation.
- Sales recorded via the eBay Fulfilment API are matched to stock by SKU.

## Analytics
- Projections: monthly turns = 30 ÷ days-to-sell on 70% deployed capital, ROI per turn = margin ÷ (1 − margin), purchases capped by `monthly_buying_capacity` (£4,000, +10%/month); worst = ½ turns at 60% margin, best = 1.3× turns at 1.2× margin.
- Listing-quality uplift is learned as mean(actual sale ÷ predicted median) − 1 over ≥ 5 sales, clamped ±30%, applied only when you press the button.
- Clone-readiness rule: last 3 months with sales all ≥ 30% margin and < 30 average days to sell.
- Weekly insights run Mondays 07:30; the mock produces a rule-based Markdown page using the same data as the Claude prompt.

## Data hygiene
- `purge_personal_data` runs daily at 03:15 and blanks seller name, location text, description and raw JSON on listings whose deals were passed/expired/never acted on more than 90 days ago. Bought deals are kept (business records).
- Logging redacts `key=`, `token=`, `secret=`, `password=`, `authorization=` patterns.

## Seed data
- 50 listings across six sources: 5 alert, ~20 are deliberately bad buys, 3 fakes/repros, 1 stock photo, 1 stolen-goods wording, 11 bundles/job lots, 8 collection-only at varying distances from Manchester, 2 auctions ending soon, 1 NTSC import.
- `MARKET` in `app/seed.py` is a hand-written approximation of UK PAL sold medians purely for the demo; real comps replace it.
- On first start in mock mode a small backdated demo history (purchases and sales) is created so P&L/accuracy pages aren't empty. It is marked in settings (`demo_history_loaded`) and never re-created.
