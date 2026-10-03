/* DealFinder first-run walkthrough. Vanilla JS, no dependencies.
   Steps live on several pages; progress is kept in sessionStorage so the tour survives navigation.
   Finishing (or skipping) POSTs /walkthrough/done so it never shows again; More -> "Show walkthrough again" resets it. */
(function () {
  const STEPS = [
    { page: "/", target: null, title: "Welcome to DealFinder",
      body: "It watches UK marketplaces for under-priced retro games, works out the real profit after every fee, and pings your phone about the good ones. <b>It never buys anything - you do.</b> This 2-minute tour shows you the basics." },
    { page: "/", target: "[data-tour=hero]", title: "Your money at a glance",
      body: "Cash available is your stock capital minus what you've bought plus what you've sold. Underneath: stock at cost, this month's realised profit and your average days to sell." },
    { page: "/", target: "[data-tour=actions]", title: "Quick actions",
      body: "Shortcuts for the things you do most. <b>Scan eBay</b> runs a search right now instead of waiting for the schedule." },
    { page: "/", target: "[data-tour=deals]", title: "Today's deals",
      body: "Each row is one listing the system thinks is worth buying. Left: where it is. Right: the <b>net profit it predicts</b> and the margin. Tap a row for the full maths." },
    { page: "/", target: "[data-tour=tabbar]", title: "Five places to go",
      body: "Home, Deals, Stock, P&amp;L and More. That's the whole app. Let's look at Deals next." },
    { page: "/deals", target: "[data-tour=chips]", title: "Filter and sort",
      body: "Chips filter by source, sort by score, profit, margin, speed or distance, and switch between open, watched, bought and passed deals. The last chip reveals listings the rules rejected, so you can see why." },
    { page: "/deals", target: "[data-tour=deals] .row", title: "Open a deal",
      body: "Tap any row to see the full breakdown. We'll open the top one now." , openFirstRow: true },
    { page: "DEAL", target: "[data-tour=hero]", title: "Predicted profit",
      body: "Green means the rules say buy. The number is what's left after buyer fees, postage or the collection trip, selling fees, packaging and a returns reserve." },
    { page: "DEAL", target: "[data-tour=decide]", title: "Your decision, not the app's",
      body: "<b>Open listing</b> takes you to the marketplace where you buy by hand. Then tap <b>Bought</b> - it becomes stock with a SKU. <b>Pass</b> hides it; <b>Watch</b> keeps it around." },
    { page: "DEAL", target: "[data-tour=money]", title: "Every line of the maths",
      body: "Landed cost, expected sale price (with how many sold recently and how sure the model is), each fee, and which rule tier applied. If a number looks wrong, the fee tables are in Settings." },
    { page: "/inventory", target: "[data-tour=chips]", title: "Stock moves through stages",
      body: "In transit → testing → ready to photograph → listed → sold → shipped. Open an item to fill in the testing checklist, generate the listing, print a SKU label and record the sale." },
    { page: "/more", target: "[data-tour=more]", title: "Everything else",
      body: "<b>Health</b> shows each source and tells you when a site needs you to log in. <b>Settings</b> holds the deal rules, fee tables (all marked VERIFY until you check them), your base location and notifications. <b>Sold data</b> is where you upload Terapeak CSVs to sharpen valuations." },
    { page: "/more", target: null, title: "You're set", final: true,
      body: "Your first-week checklist:<ul style='margin:.5rem 0 0 1.1rem;padding:0'><li>Set your base postcode in Settings</li><li>Verify the fee and postage defaults</li><li>Install the ntfy app and paste your topic in .env</li><li>Upload a Terapeak CSV for your main platforms</li></ul>Everything is in SETUP_CHECKLIST.md. You can replay this tour from More." },
  ];
  const KEY = "df_tour_step", DEAL_KEY = "df_tour_deal";
  const body = document.body;
  if (body.dataset.tour !== "on") return;
  let step = parseInt(sessionStorage.getItem(KEY) || "0", 10);
  if (isNaN(step) || step < 0 || step >= STEPS.length) step = 0;

  function pageFor(s) { return s.page === "DEAL" ? (sessionStorage.getItem(DEAL_KEY) || "/deals") : s.page; }
  function onRightPage(s) {
    const want = pageFor(s);
    if (s.page === "DEAL") return /^\/deals\/\d+/.test(location.pathname);
    return location.pathname === want;
  }
  function go(n) {
    step = n;
    sessionStorage.setItem(KEY, String(step));
    const s = STEPS[step];
    if (!onRightPage(s)) { location.href = pageFor(s); return; }
    render();
  }
  function finish() {
    sessionStorage.removeItem(KEY); sessionStorage.removeItem(DEAL_KEY);
    fetch("/walkthrough/done", { method: "POST" }).finally(() => { teardown(); body.dataset.tour = "off"; });
  }

  // --- overlay ---------------------------------------------------------
  let overlay, spot, tip;
  function build() {
    overlay = document.createElement("div"); overlay.className = "tour-overlay";
    spot = document.createElement("div"); spot.className = "tour-spot";
    tip = document.createElement("div"); tip.className = "tour-tip";
    document.body.append(overlay, spot, tip);
    window.addEventListener("resize", render);
  }
  function teardown() { [overlay, spot, tip].forEach(e => e && e.remove()); window.removeEventListener("resize", render); }
  function render() {
    if (!overlay) build();
    const s = STEPS[step];
    const el = s.target ? document.querySelector(s.target) : null;
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "instant" });
      const r = el.getBoundingClientRect(), pad = 8;
      spot.style.display = "block";
      Object.assign(spot.style, { top: (r.top - pad) + "px", left: (r.left - pad) + "px", width: (r.width + 2 * pad) + "px", height: (r.height + 2 * pad) + "px" });
      overlay.style.background = "transparent";
      const below = r.bottom + 16, spaceBelow = window.innerHeight - r.bottom;
      tip.style.top = (spaceBelow > 260 || r.top < 200) ? Math.min(below, window.innerHeight - 240) + "px" : Math.max(16, r.top - 16 - 230) + "px";
      tip.style.bottom = "auto";
    } else {
      spot.style.display = "none";
      overlay.style.background = "rgba(5,8,20,.72)";
      tip.style.top = "auto"; tip.style.bottom = "90px";
    }
    tip.innerHTML =
      `<div class="tour-progress">${step + 1} of ${STEPS.length}</div><h3>${s.title}</h3><p>${s.body}</p>` +
      `<div class="tour-btns">` +
      (step > 0 ? `<button class="btn btn-grey btn-sm" data-act="back">Back</button>` : `<span></span>`) +
      `<span style="flex:1"></span>` +
      (s.final ? `<button class="btn btn-green" data-act="done">I understand the basics</button>`
               : `<button class="btn btn-grey btn-sm" data-act="skip">Skip</button><button class="btn btn-primary btn-sm" data-act="next">Next</button>`) +
      `</div>`;
    tip.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", () => {
      const act = b.dataset.act;
      if (act === "back") go(step - 1);
      else if (act === "skip" || act === "done") finish();
      else if (act === "next") {
        if (s.openFirstRow) {
          const row = document.querySelector("[data-tour=deals] .row[href]");
          sessionStorage.setItem(DEAL_KEY, row ? row.getAttribute("href") : "/deals/1");
        }
        go(step + 1);
      }
    }));
  }
  const s = STEPS[step];
  if (!onRightPage(s)) { if (step === 0) { /* first open on another page: start from home */ sessionStorage.setItem(KEY, "0"); } location.href = pageFor(s); return; }
  render();
})();
