"""Probe 1 + 2 — Reddit unblock attempts.

Probe 1: read reddit.com cookies from Chrome, hit JSON API with them.
Probe 2: use the production BrowserTier (Camoufox) to fetch the listing URL.

No production code modified. Pure investigation.
"""

from __future__ import annotations

import asyncio

from curl_cffi import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"


def _read_reddit_cookies() -> dict[str, str]:
    try:
        from a2web.packages.cookie_store import read_cookies

        rows = read_cookies("chrome", domain=".reddit.com")
    except Exception as exc:
        print(f"  COOKIE READ ERROR: {type(exc).__name__}: {exc}")
        return {}
    out = {}
    for row in rows:
        if "reddit.com" in (row.host or ""):
            out[row.name] = row.value
    return out


async def probe_with_cookies(label: str, url: str, cookies: dict[str, str]) -> None:
    print(f"\n=== {label} :: {url} ===")
    print(f"  cookies attached: {len(cookies)}")
    if not cookies:
        print("  (no cookies — Chrome may be running and locking the DB, or Keychain prompt was declined)")
    try:
        r = await asyncio.to_thread(
            requests.get,
            url,
            impersonate="chrome",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            cookies=cookies,
            timeout=15,
            allow_redirects=True,
        )
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return
    body = r.text or ""
    print(f"  status: {r.status_code}  ct: {r.headers.get('content-type', '?')}  len: {len(body)}")
    snippet = body[:200].replace("\n", " ⏎ ")
    print(f"  body[:200]: {snippet!r}")
    if "json" in r.headers.get("content-type", "").lower():
        try:
            import json

            payload = json.loads(body)
            children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
            print(f"  ✓ JSON parsed: {len(children)} children")
        except Exception as exc:
            print(f"  ✗ JSON parse failed: {exc}")


async def probe_browser_tier(url: str) -> None:
    """Skip the full AppState; just exercise BrowserPool + a raw Playwright page."""
    print(f"\n=== browser-tier :: {url} ===")
    try:
        from a2web.packages.browser_pool import BrowserPool
    except Exception as exc:
        print(f"  IMPORT ERROR: {exc}")
        return

    pool = BrowserPool()
    try:
        async with pool:
            print("  launching Camoufox...")
            async with pool.acquire(url) as page:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status = resp.status if resp else "?"
                await asyncio.sleep(4)  # let React hydrate
                content = await page.content()
                title = await page.title()
                print(f"  status: {status}")
                print(f"  title: {title!r}")
                print(f"  body len: {len(content)} chars")
                # Block-page sniffs
                if "blocked" in content.lower():
                    print("  ⚠ 'blocked' appears in DOM")
                # Post evidence
                if "LocalLLaMA" in content:
                    print("  ✓ subreddit name visible in DOM")
                post_count = content.count('href="/r/LocalLLaMA/comments/')
                print(f"  post-link references: {post_count}")
                snippet = content[:300].replace("\n", " ⏎ ")
                print(f"  body[:300]: {snippet!r}")
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")


async def main() -> None:
    print("=" * 60)
    print("PROBE 1 — JSON API with Chrome cookies attached")
    print("=" * 60)
    cookies = _read_reddit_cookies()
    print(f"Loaded {len(cookies)} reddit.com cookies from Chrome.")
    if cookies:
        print(f"Cookie names: {sorted(cookies.keys())}")
    await probe_with_cookies("json-api+cookies", "https://www.reddit.com/r/LocalLLaMA/.json", cookies)
    await probe_with_cookies("www-html+cookies", "https://www.reddit.com/r/LocalLLaMA/", cookies)

    print("\n" + "=" * 60)
    print("PROBE 2 — Browser tier (Camoufox)")
    print("=" * 60)
    await probe_browser_tier("https://www.reddit.com/r/LocalLLaMA/")


if __name__ == "__main__":
    asyncio.run(main())
