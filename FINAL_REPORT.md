# Final report

## What's built (and runs)

`docker compose up --build` (Postgres + ntfy + app) or `make run` (SQLite) starts the whole system; 79 offline tests pass
(`make test`); lint is clean (`make lint`). In mock mode it seeds 50 realistic listings, scores them (5 alert, 3 fakes
blocked, bundles valued as the sum of parts, far-away collections rejected on trip cost), and creates a small demo
stock history so every dashboard page has data.

| Module | Status |
|---|---|
| 1 Sourcing | eBay Browse API client (real + mock); browser helper with pacing, quiet hours, hourly cap, pause-on-block + push; 5 site selector configs + fixture pages; de-dupe (exact + fuzzy cross-post); paid-feed stub; per-source scheduler jobs |
| 2 Identification & valuation | Claude SDK client + rule-based mock; prompts versioned in `/prompts`; risk flags; `SoldDataProvider` × 4 (Insights, CSV, own sales, mock); median/IQR/sold/active/sell-through/days/confidence; 24 h cache |
| 3 Profit engine | Full landed P&L incl. buyer fees, inbound postage or collection fuel/time by distance; tiered rules, large-deal relief, phase mode, £8 floor, low-confidence, capital reserve, 0–100 score; editable fee/postage tables with VERIFY flags |
| 4 Notifications | ntfy + Pushover + mock behind `Notifier`; priority/sound, 30-min digest, 8am summary, source/task pushes, quiet hours |
| 5 Inventory & listing | SKU + PDF label, status flow, niche testing checklist, listing generator (≤80-char title, honest copy, specifics, price + markdowns, shot list), eBay Sell API (real + mock), cross-list CSV + `CrossLister`, auto-end eBay / urgent task on sale, real-fee sales + Fulfilment sync |
| 6 Dashboard | Home, deals feed, kanban, P&L with predicted-vs-actual, projections, weekly tips + clone rule, settings, niches, health, sold-data upload |

## What's mocked until you add keys (see SETUP_CHECKLIST.md)

- **Claude**: `MockLLMClient` (rule-based normaliser / flags / copy / insights) until `ANTHROPIC_API_KEY` is set.
- **eBay Browse search**: `MockEbayBrowseWatcher` over the seed listings until `EBAY_CLIENT_ID/SECRET` are set.
- **eBay sold data**: `EbayMarketplaceInsightsProvider` returns nothing until access is granted; the mock comps table stands in. CSV upload and your own sales are real today.
- **eBay selling**: `MockEbaySellClient` until `EBAY_SELL_OAUTH_TOKEN` (+ business policy IDs) exist.
- **Browser sources**: read fixture HTML in mock mode; real browsing needs `BROWSER_SOURCES_ENABLED=true` and a one-off login per site.
- **Push**: `MockNotifier` logs to stdout until `NOTIFIER=ntfy|pushover` with a topic/keys.
- **Distances**: postcode-area centroids + a town table (approximate by design, not a routing API).
- **Image hashes**: cross-post detection uses title + price; perceptual hashes are only used when an image hash is present (images are not downloaded yet).

## What to do next (in order)

1. Run through `SETUP_CHECKLIST.md` — base location, verify fees/postage, Claude key, eBay keys, ntfy app.
2. Upload a Terapeak CSV per platform so valuations reach "high" confidence (15+ comps); watch the Deals feed with
   "include non-alerts" for a day to sanity-check prices before trusting alerts.
3. Log in to the marketplaces once (`make helper-login`), enable sources one at a time, fix selectors as sites change (RUNBOOK.md).
4. After the first 5–10 sales: P&L → "Apply learned uplift"; review the days-to-sell heuristic against your actuals (`estimate_days_to_sell` in `app/identification/valuation.py`) and the tier rules.
5. Engineering follow-ups, by value: eBay OAuth refresh-token flow for the Sell APIs; downloading listing images to compute perceptual hashes for cross-post de-dupe; a real cross-lister integration behind `CrossLister`; a plug-in for the paid data feed if the browser helper misses deals; HTMX partial refresh on the deals feed; basic auth on the dashboard if exposed beyond your LAN.
