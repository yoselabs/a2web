"""Probe — does Camoufox actually bypass Cloudflare in our setup?

Hits 3-4 known-Cloudflare-protected URLs with raw curl_cffi (production
config: impersonate=chrome) AND with the production BrowserPool. Reports
status, body length, and whether the body contains real content vs the
CF challenge interstitial.

Decision input: should planner route CF-403/anti-bot to browser BEFORE
archive, or keep archive as primary? Camoufox wins if it returns real
content where raw gets the 'Just a moment...' interstitial.

No production code modified.
"""

from __future__ import annotations

import asyncio
import re

from curl_cffi import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

# Known Cloudflare-protected sites, varying aggression levels.
# nowsecure.nl  — classic CF Turnstile demo (always challenges)
# discord.com   — CF-protected, JS-challenge on first hit
# medium.com    — CF-protected, mild
# www.nse.com.au — CF + heavy fingerprinting (financial site)
TARGETS = [
    ("nowsecure", "https://nowsecure.nl/"),
    ("discord-home", "https://discord.com/"),
    ("medium", "https://medium.com/"),
]

# CF interstitial markers in the body
_CF_INTERSTITIAL = re.compile(
    r"Just a moment|Checking your browser|cf-browser-verification|cf_chl_opt|__cf_chl|Enable JavaScript and cookies to continue",
    re.IGNORECASE,
)


async def probe_raw(label: str, url: str) -> dict:
    print(f"\n--- raw :: {label} :: {url}")
    try:
        r = await asyncio.to_thread(
            requests.get,
            url,
            impersonate="chrome",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=20,
            allow_redirects=True,
        )
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return {"verdict": "error"}
    body = r.text or ""
    is_cf_interstitial = bool(_CF_INTERSTITIAL.search(body))
    cf_ray = r.headers.get("cf-ray", "")
    server = r.headers.get("server", "")
    print(f"  status: {r.status_code}  len: {len(body)}  cf-ray: {cf_ray[:14]!r}  server: {server!r}")
    print(f"  cf_interstitial_in_body: {is_cf_interstitial}")
    verdict = "blocked-403" if r.status_code == 403 else (
        "cf-challenge" if is_cf_interstitial else ("ok" if r.status_code == 200 and len(body) > 5000 else "thin")
    )
    print(f"  → verdict: {verdict}")
    return {"verdict": verdict, "status": r.status_code, "len": len(body), "cf_ray": bool(cf_ray)}


async def probe_browser(label: str, url: str) -> dict:
    print(f"\n--- browser :: {label} :: {url}")
    try:
        from a2web.packages.browser_pool import BrowserPool
    except Exception as exc:
        print(f"  IMPORT ERROR: {exc}")
        return {"verdict": "error"}

    pool = BrowserPool()
    try:
        async with pool:
            async with pool.acquire(url) as page:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = resp.status if resp else 0
                # Allow CF challenge to auto-solve + JS hydration
                await asyncio.sleep(6)
                content = await page.content()
                title = await page.title()
                is_interstitial = bool(_CF_INTERSTITIAL.search(content))
                print(f"  status: {status}  len: {len(content)}  title: {title!r}")
                print(f"  cf_interstitial_in_body: {is_interstitial}")
                verdict = "blocked-403" if status == 403 else (
                    "cf-challenge" if is_interstitial else ("ok" if status == 200 and len(content) > 10000 else "thin")
                )
                print(f"  → verdict: {verdict}")
                return {"verdict": verdict, "status": status, "len": len(content)}
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return {"verdict": "error"}


async def main() -> None:
    results: list[tuple[str, dict, dict]] = []
    for label, url in TARGETS:
        print("\n" + "=" * 60)
        print(f"TARGET: {label} — {url}")
        print("=" * 60)
        raw = await probe_raw(label, url)
        browser = await probe_browser(label, url)
        results.append((label, raw, browser))

    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'target':<20}{'raw':<20}{'browser':<20}{'browser wins?':<15}")
    for label, raw, browser in results:
        raw_v = raw.get("verdict", "?")
        br_v = browser.get("verdict", "?")
        wins = "yes" if (raw_v in ("blocked-403", "cf-challenge", "thin") and br_v == "ok") else ("no" if raw_v == br_v else "partial")
        print(f"{label:<20}{raw_v:<20}{br_v:<20}{wins:<15}")


if __name__ == "__main__":
    asyncio.run(main())
