"""SPIKE 6.1 — does .json + logged-in Chrome cookies pass Datadome?

Reads reddit.com cookies from Chrome, then replays them through curl_cffi
(chrome120 impersonation — same as a2web's raw tier) against .json endpoints.
A no-cookie control confirms the wall is real. Cookie VALUES are never printed.
"""

from __future__ import annotations

import asyncio

from curl_cffi import requests as cr

from a2web.packages.cookie_store import read_cookies

_IMPERSONATE = "chrome120"
_INTERESTING = {"datadome", "reddit_session", "token_v2", "loid", "edgebucket", "session", "csv", "session_tracker"}

# A listing and the original failing search from the exploration. The thread
# target is derived at runtime from a real permalink in the listing response.
_TARGETS = [
    ("listing", "https://www.reddit.com/r/gravelcycling/hot.json?limit=5"),
    ("search", "https://www.reddit.com/r/gravelcycling/search.json?q=bell&restrict_sr=1&sort=top"),
]


def _classify(status: int, body: bytes) -> str:
    head = body[:400].decode("utf-8", errors="replace").lower()
    if status == 200 and (body.lstrip().startswith(b"{") or body.lstrip().startswith(b"[")):
        return "✅ JSON (passed)"
    if "datadome" in head or "captcha-delivery" in head or "geo.captcha" in head:
        return "🛑 Datadome block page"
    if "just a moment" in head or "cf-" in head:
        return "🛑 Cloudflare interstitial"
    if status == 403:
        return "🛑 403 (walled)"
    return f"❓ status={status}, non-JSON"


async def _fetch(url: str, cookies: dict[str, str] | None) -> tuple[int, bytes]:
    kwargs = {"headers": {"User-Agent": "Mozilla/5.0"}, "timeout": 20, "allow_redirects": True}
    if cookies:
        kwargs["cookies"] = cookies
    async with cr.AsyncSession(impersonate=_IMPERSONATE) as s:
        r = await s.get(url, **kwargs)
        return r.status_code, r.content


async def main() -> None:
    print("Reading reddit.com cookies from Chrome (Keychain prompt expected)...\n")
    rows = read_cookies("chrome", domain="reddit.com")
    cookies = {row.name: row.value for row in rows}
    present = sorted(n for n in cookies if n in _INTERESTING)
    print(f"Cookies read: {len(cookies)} total for reddit.com")
    print(f"Relevant cookies PRESENT (values redacted): {present}")
    print(f"  datadome token present: {'datadome' in cookies}")
    print(f"  logged-in signal (reddit_session/token_v2/loid): "
          f"{any(k in cookies for k in ('reddit_session', 'token_v2', 'loid'))}\n")
    print("=" * 70)

    thread_url: str | None = None
    for label, url in _TARGETS:
        print(f"\n### {label}: {url}")
        try:
            s0, b0 = await _fetch(url, None)
            print(f"  NO cookies : {_classify(s0, b0)}  (len={len(b0)})")
        except Exception as e:  # noqa: BLE001 — spike, report and continue
            print(f"  NO cookies : ERROR {type(e).__name__}: {e}")
        try:
            s1, b1 = await _fetch(url, cookies)
            print(f"  WITH cookies: {_classify(s1, b1)}  (len={len(b1)})")
            # Derive a real thread permalink from the listing response.
            if label == "listing" and s1 == 200 and thread_url is None:
                import json

                try:
                    data = json.loads(b1)
                    perma = data["data"]["children"][0]["data"]["permalink"]
                    thread_url = f"https://www.reddit.com{perma}.json"
                except Exception:  # noqa: BLE001
                    thread_url = None
        except Exception as e:  # noqa: BLE001
            print(f"  WITH cookies: ERROR {type(e).__name__}: {e}")

    if thread_url:
        print(f"\n### thread (derived): {thread_url}")
        s0, b0 = await _fetch(thread_url, None)
        print(f"  NO cookies : {_classify(s0, b0)}  (len={len(b0)})")
        s1, b1 = await _fetch(thread_url, cookies)
        print(f"  WITH cookies: {_classify(s1, b1)}  (len={len(b1)})")
    else:
        print("\n### thread: skipped (listing didn't yield a permalink)")


if __name__ == "__main__":
    asyncio.run(main())
