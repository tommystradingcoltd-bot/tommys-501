"""Open the persistent helper browser (headed) so you can sign in to each marketplace by hand, once.

Usage:  python -m scripts.helper_login [site ...]
The profile is saved in BROWSER_PROFILE_DIR; the watchers reuse it. Nothing here logs in automatically.
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.sourcing.browser.parser import load_selectors

SITES = ["facebook", "vinted", "gumtree", "shpock", "depop"]


def main() -> None:
    from playwright.sync_api import sync_playwright
    s = get_settings()
    sites = [a for a in sys.argv[1:] if a in SITES] or SITES
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(s.browser_profile_dir, headless=False, viewport={"width": 1280, "height": 900},
                                                    locale="en-GB", timezone_id="Europe/London")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for site in sites:
            url = load_selectors(site)["base_url"]
            print(f"\n==> {site}: log in in the browser window, then press Enter here.")
            page.goto(url)
            input()
        ctx.close()
    print(f"Done. Profile saved in {s.browser_profile_dir}. Set BROWSER_SOURCES_ENABLED=true and enable the sources in Settings.")


if __name__ == "__main__":
    main()
