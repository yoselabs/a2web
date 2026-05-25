"""Diagnostic probe — what does Reddit serve unauth curl_cffi clients today?

Three URLs, three questions:
  1. www.reddit.com/r/LocalLLaMA/.json — the handler's JSON API call
  2. www.reddit.com/r/LocalLLaMA/      — the raw tier's HTML call
  3. old.reddit.com/r/LocalLLaMA/      — the candidate fallback

For each: status code, body length, content-type, first 300 chars (for the
"is this a login wall" eyeball), and the curl_cffi error if any.

No production code modified. Pure investigation.
"""

from __future__ import annotations

import asyncio

from curl_cffi import requests

# Match the production default UA so we're probing what the raw tier actually sees.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

URLS = [
    ("json-api", "https://www.reddit.com/r/LocalLLaMA/.json"),
    ("www-html", "https://www.reddit.com/r/LocalLLaMA/"),
    ("old-html", "https://old.reddit.com/r/LocalLLaMA/"),
]


async def probe_one(label: str, url: str) -> None:
    print(f"\n=== {label} :: {url} ===")
    try:
        # impersonate=chrome matches the raw tier configuration
        r = await asyncio.to_thread(
            requests.get,
            url,
            impersonate="chrome",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=15,
            allow_redirects=True,
        )
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return

    body = r.text or ""
    ct = r.headers.get("content-type", "?")
    final = r.url
    print(f"  status: {r.status_code}")
    print(f"  final_url: {final}")
    print(f"  content-type: {ct}")
    print(f"  body len: {len(body)} chars")
    snippet = body[:300].replace("\n", " ⏎ ")
    print(f"  body[:300]: {snippet!r}")
    # Common Reddit anti-bot markers
    markers = []
    if "blocked" in body.lower():
        markers.append("'blocked'")
    if "login" in body.lower() and "register" in body.lower():
        markers.append("login+register")
    if "error" in body.lower() and "429" in body:
        markers.append("error+429")
    if "captcha" in body.lower():
        markers.append("captcha")
    if "verify" in body.lower():
        markers.append("verify")
    print(f"  block markers: {markers or 'none'}")


async def main() -> None:
    for label, url in URLS:
        await probe_one(label, url)


if __name__ == "__main__":
    asyncio.run(main())
