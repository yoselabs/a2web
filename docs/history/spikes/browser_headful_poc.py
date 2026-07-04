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

async def run(headless, cookies, label):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:
            ctx = await browser.new_context()
            if cookies: await ctx.add_cookies([to_pw(c) for c in cookies])
            page = await ctx.new_page()
            try:
                resp = await asyncio.wait_for(page.goto("https://www.reddit.com/r/gravelcycling/", wait_until="domcontentloaded"), timeout=45)
                status = resp.status if resp else "?"
            except asyncio.TimeoutError:
                status = "timeout"
            await page.wait_for_timeout(3000)
            body = await page.evaluate("() => document.body ? document.body.innerText.slice(0,200) : ''")
            posts = await page.evaluate("() => document.querySelectorAll('shreddit-post, article').length")
            blocked = "blocked by network" in body.lower() or "whoa there" in body.lower()
            verdict = "🛑 BLOCKED" if blocked else (f"✅ PASSED ({posts} posts)" if posts else "❓ unclear")
            print(f"### {label}: status={status} posts={posts} -> {verdict}")
            print(f"   body[:120]: {body[:120]!r}")
        finally:
            await browser.close()

async def main():
    rows = list(read_cookies("chrome", domain="reddit.com"))
    await run(True,  None, "HEADLESS no-cookies")
    await run(False, None, "HEADFUL  no-cookies")
    await run(False, rows, "HEADFUL  with-cookies")

asyncio.run(main())
