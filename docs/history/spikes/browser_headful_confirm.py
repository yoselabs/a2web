import asyncio
from patchright.async_api import async_playwright
from a2web.packages.cookie_store import read_cookies

def to_pw(row):
    d = {"name": row.name, "value": row.value, "path": row.path or "/",
         "secure": bool(row.is_secure), "httpOnly": bool(row.is_httponly),
         "expires": row.expires_utc if row.expires_utc else -1,
         "domain": row.host_key or ".reddit.com"}
    if row.samesite: d["sameSite"] = row.samesite.capitalize()
    return d

TARGETS = [
    ("search (original fail)", "https://www.reddit.com/r/gravelcycling/search/?q=bell&restrict_sr=1&sort=top"),
    ("hot listing", "https://www.reddit.com/r/gravelcycling/"),
]

async def main():
    rows = list(read_cookies("chrome", domain="reddit.com"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        await ctx.add_cookies([to_pw(c) for c in rows])
        try:
            for label, url in TARGETS:
                page = await ctx.new_page()
                try:
                    r = await asyncio.wait_for(page.goto(url, wait_until="domcontentloaded"), timeout=45)
                    await page.wait_for_timeout(3500)
                    posts = await page.evaluate("() => document.querySelectorAll('shreddit-post, article, [data-testid=\"post-container\"]').length")
                    body = await page.evaluate("() => document.body.innerText.slice(0,180)")
                    blocked = "blocked by network" in body.lower()
                    print(f"### {label}: status={r.status} posts={posts} -> {'🛑 BLOCKED' if blocked else '✅ PASSED'}")
                    print(f"   sample: {body[:150]!r}\n")
                finally:
                    await page.close()
            # derive a thread from the listing and open it
            page = await ctx.new_page()
            await page.goto("https://www.reddit.com/r/gravelcycling/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            href = await page.evaluate("""() => { const a=document.querySelector('a[href*=\"/comments/\"]'); return a?a.href:null; }""")
            if href:
                await page.goto(href, wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                comments = await page.evaluate("() => document.querySelectorAll('shreddit-comment').length")
                print(f"### thread {href[:70]}...: comments rendered={comments} -> {'✅' if comments else '❓'}")
            await page.close()
        finally:
            await browser.close()

asyncio.run(main())
