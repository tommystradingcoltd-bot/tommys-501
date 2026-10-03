# Setup checklist — the only things you have to do by hand

Everything runs in mock mode out of the box. Each step below unlocks a real integration. Do them in any order.

## 1. Run it once (5 min)
- [ ] `cp .env.example .env`
- [ ] `docker compose up --build` (or `make install && make run` for SQLite) and open http://localhost:8000
- [ ] Open it on your phone on the same Wi-Fi (`http://<your-pc-ip>:8000`) — the UI is designed for a phone.

## 2. Set your base location (1 min)
- [ ] Settings → Base location → enter your office postcode district (e.g. `M1`). Change it whenever you travel;
      collection-only deals are costed from this point. Also check Settings → Deal rules → "Max collection miles".

## 3. Verify the fee and postage defaults (15 min, important)
The seeded numbers are **starting guesses marked VERIFY**, not facts. Check each against the live fee page and tick
"verified" in Settings → Fees / Postage. The ones that matter most:
- [ ] eBay final value fee for Video Games (currently seeded 12.8% + 30p + 0.35% regulatory fee). Note eBay UK private
      sellers have had 0% selling fees since 2024 — if you sell as a private seller, set `ebay_fvf_pct` accordingly; if
      as a business seller, use your category rate.
- [ ] eBay **buyer** protection fee when *you* buy from private sellers (seeded 4% + 75p).
- [ ] Vinted buyer protection (seeded 5% + 70p), Depop and Shpock buyer fees.
- [ ] Royal Mail large letter / small parcel / medium parcel and Evri rates (Settings → Postage). Set one default per class.
- [ ] Packaging costs, fault/return reserve %, fuel pence per mile, your hourly rate for collections.

## 4. Claude API key (2 min) — unlocks real normalisation, risk flags, listing copy and weekly insights
- [ ] Create a key at https://console.anthropic.com → `ANTHROPIC_API_KEY=sk-ant-...` in `.env`.
- [ ] Optional: change `CLAUDE_MODEL` (default `claude-opus-5-5`).
- [ ] Set `MOCK_MODE=false` and restart. Without a key the rule-based mock keeps everything running.

## 5. eBay developer keys (15 min) — unlocks live eBay search (Browse API)
- [ ] Register at https://developer.ebay.com → create a **Production** keyset.
- [ ] Paste `EBAY_CLIENT_ID` (App ID) and `EBAY_CLIENT_SECRET` (Cert ID) into `.env`. `EBAY_MARKETPLACE_ID=EBAY_GB`.
- [ ] The Browse API works with client-credentials straight away. Restart; Health should show eBay "ok".

## 6. eBay sold-price data (apply, then wait)
- [ ] Apply for **Marketplace Insights API** access (restricted; it's an application form in the eBay developer portal
      under "API access requests"). When granted, set `EBAY_MARKETPLACE_INSIGHTS_ENABLED=true`.
- [ ] Meanwhile: export sold data by hand from **Terapeak** (eBay Seller Hub → Research) as CSV and upload it on the
      Sold data page. Columns recognised: title, sold price, date sold, platform, region, completeness. Do this for
      the platforms you buy most (SNES, N64, PS1, Game Boy...). The valuation marks items "low confidence" until it has
      5+ comps, so more CSV = better alerts.
- [ ] Your own sales feed in automatically and gain weight over time.

## 7. eBay selling (when you're ready to list)
- [ ] In the developer portal, generate a **User token** for your seller account with the Sell scopes
      (`sell.inventory`, `sell.fulfillment`). Paste as `EBAY_SELL_OAUTH_TOKEN`. (Tokens expire; refresh-token flow is
      a follow-up — see "What next" in the final report.)
- [ ] Create your business policies (postage, returns, payment) in Seller Hub and note their IDs; add them to
      `app/inventory/ebay_sell.py` → `RealEbaySellClient.publish` (`fulfillmentPolicyId` etc.).
- [ ] Until then, "Mark listed" with platform "eBay" uses the mock and you list by hand.

## 8. Phone push notifications (5 min)
- [ ] Install the **ntfy** app (Android/iOS). Subscribe to a long random topic, e.g. `dealfinder-7f3a9c2e-k1`.
- [ ] `.env`: `NOTIFIER=ntfy`, `NTFY_TOPIC=<that topic>`, `NTFY_SERVER=https://ntfy.sh` (or `http://ntfy:80` to use the
      bundled self-hosted server — then point the app at `http://<your-pc-ip>:8080`).
- [ ] `DASHBOARD_BASE_URL=http://<your-pc-ip>:8000` so the deal links in notifications open on your phone.
- [ ] Settings → Notifications → "Send test notification".
- [ ] Alternative: Pushover (`NOTIFIER=pushover`, `PUSHOVER_USER_KEY`, `PUSHOVER_APP_TOKEN`).

## 9. Browser helper: sign in to each marketplace once (10 min)
- [ ] On the machine that will run the watchers: `make install` (installs Chromium) then `make helper-login`.
      A browser window opens on each site in turn; log in by hand, press Enter in the terminal, repeat.
      The profile is saved in `BROWSER_PROFILE_DIR` (default `./data/browser_profile`).
- [ ] `.env`: `BROWSER_SOURCES_ENABLED=true`. Keep `BROWSER_HEADLESS=true` (set false to watch it).
- [ ] Settings → Sources: enable Facebook / Vinted / Gumtree / Shpock / Depop and check the pacing limits
      (defaults: 45–120 s between pages, 40 pages/hour, quiet 23:00–07:00).
- [ ] Facebook Marketplace: set `location_slug` in `app/sourcing/browser/selectors/facebook.yaml` to your city.
- [ ] Expect to fix selectors occasionally (sites change). RUNBOOK.md shows how; no code changes needed.
- [ ] In Docker the helper runs inside the container; log in on the host first and mount `./data` (already in compose),
      or run the watchers on the host with `make run` instead.

## 10. Tune the deal rules (ongoing)
- [ ] Settings → Deal rules: phase mode (Capital Growth for ~3 months, then Steady), tiers, profit floor, reserve.
- [ ] After 5+ sales, P&L page → "Apply learned uplift" sets the listing-quality uplift from your real results.

## 11. Backups
- [ ] `make backup` weekly (Postgres dump or SQLite copy into `backups/`). See RUNBOOK.md for restore.
