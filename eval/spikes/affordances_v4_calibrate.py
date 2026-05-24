"""Spike v4 — confidence calibration on the V_CTX prompt.

v2 found that V_CTX classifies pages reasonably well (63% literal, ~80%
semantic) but ALL classifications came back `confidence: high` — including
on the obvious failures (404 page reported as paywalled, comment thread
reported as status page, etc.). Confidence is therefore useless to a
downstream agent — it's a constant.

This spike iterates V_CTX with:

  - Explicit `error` / `empty` exits added to the page_kind enum so the
    model has an honest way out of 404 / cookie-wall / blocked pages
  - Hard rules forcing `low` confidence when:
      (a) content_md < 500 chars
      (b) shape signals conflict (e.g. nav + footer only, no body)
      (c) the page kind is uncertain between two close labels
  - A short rubric in the prompt that names cases the model often
    misclassified in v2 (changelog vs listing, readme vs package-page)

We run it twice: once on the 14 weak cases for fast iteration, then on
the full 30-URL corpus to confirm we didn't regress the easy cases.

Run:
    uv run python eval/spikes/affordances_v4_calibrate.py [--full]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

from purgatory import AsyncCircuitBreakerFactory

from a2web.fetcher import fetch
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from a2web.packages.proxy_routing import ProxyPool, ProxyEntryShape, RouteRuleShape
from a2web.server import build_browser_pool, build_llm_extractor
from a2web.settings import AppSettings
from a2web.state import SqliteResource, build_state


PRIMER_ASK = "Give a 2-3 sentence summary of what this page is."


# Full 30-URL corpus (kept in sync with v2/v3).
URLS_FULL: list[tuple[str, str, str]] = [
    ("tiny-arxiv",          "article-short", "https://arxiv.org/abs/2402.17753"),
    ("tiny-gh-gist",        "code-snippet",  "https://gist.github.com/jboner/2841832"),
    ("tiny-status-page",    "status",        "https://status.openai.com/"),
    ("huge-wikipedia",      "encyclopedia",  "https://en.wikipedia.org/wiki/Rust_(programming_language)"),
    ("huge-mdn-array",      "api-reference", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array"),
    ("huge-changelog",      "changelog",     "https://github.com/pydantic/pydantic/releases"),
    ("listing-hn",          "listing",       "https://news.ycombinator.com/"),
    ("listing-lobste",      "listing",       "https://lobste.rs/active"),
    ("listing-gh-trending", "listing",       "https://github.com/trending/python?since=daily"),
    ("listing-pypi",        "package-page",  "https://pypi.org/project/httpx/"),
    ("comments-hn-item",    "threaded",      "https://news.ycombinator.com/item?id=39745700"),
    ("comments-lobste",     "threaded",      "https://lobste.rs/s/n1gytv"),
    ("docs-fastapi",        "tutorial",      "https://fastapi.tiangolo.com/tutorial/first-steps/"),
    ("docs-postgres",       "api-reference", "https://www.postgresql.org/docs/current/sql-select.html"),
    ("docs-anthropic",      "api-reference", "https://docs.claude.com/en/api/messages"),
    ("ref-rfc",             "spec",          "https://datatracker.ietf.org/doc/html/rfc9110"),
    ("ref-mdn-fetch",       "api-reference", "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API"),
    ("news-bbc",            "news-article",  "https://www.bbc.com/news/articles/cjwp82ye4y3o"),
    ("blog-julia-evans",    "blog-post",     "https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/"),
    ("forum-so-question",   "qa",            "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python"),
    ("code-gh-file",        "source-file",   "https://github.com/pydantic/pydantic/blob/main/pydantic/main.py"),
    ("code-gh-readme",      "readme",        "https://github.com/encode/httpx"),
    ("product-amazon",      "product-page",  "https://www.amazon.com/dp/B0BSHF7WHW"),
    ("media-yt-video",      "video-page",    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("gov-sec-filing",      "filing",        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=10-K&dateb=&owner=include&count=40"),
    ("spa-react-dev",       "spa",           "https://react.dev/learn"),
    ("data-json-feed",      "json-feed",     "https://hnrss.org/frontpage.jsonfeed"),
    ("gated-nyt",           "paywalled",     "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html"),
    ("paper-arxiv-pdf-stub","pdf-stub",      "https://arxiv.org/pdf/2402.17753"),
    ("docs-cf-page",        "marketing",     "https://www.cloudflare.com/products/registrar/"),
]

# 14 weak cases extracted from v2 — fast iteration loop.
WEAK_SLUGS = {
    "tiny-arxiv", "tiny-gh-gist", "tiny-status-page", "huge-changelog",
    "comments-lobste", "docs-anthropic", "news-bbc", "blog-julia-evans",
    "code-gh-readme", "media-yt-video", "spa-react-dev", "gated-nyt",
    "paper-arxiv-pdf-stub", "docs-cf-page",
}


V_CTX_V2_SYSTEM = (
    "You are an extraction helper. You classify the page TYPE and emit affordances "
    "tuned to that type. You are honest about uncertainty: when content is thin, "
    "blocked, or ambiguous, you SAY SO via the page_kind enum and the confidence "
    "field. You do not pretend a page is full when it is not. Output strict JSON only."
)


V_CTX_V2_TEMPLATE = """Web page content (chars={n_chars}):
{content}

Primary question: {ask}

STEP 1 — Classify the page. Pick the ONE best `page_kind` from this closed set:

  Content kinds:
    listing | thread | reference | api-reference | tutorial | article-short |
    article-long | changelog | code-snippet | source-file | readme | qa | spec |
    filing | news-article | blog-post | product-page | video-page | json-feed |
    marketing | encyclopedia | package-page | pdf-stub | spa
  Failure / honest-exit kinds:
    paywalled    — clear paywall language, partial content visible
    error        — 404, 500, broken page, "not found"
    empty        — nav + footer only, no real body content
    blocked      — captcha, bot wall, cloudflare interstitial
    other        — page exists but doesn't fit any label above

STEP 2 — Set `page_kind_confidence` honestly using these rules:

  Force `low` confidence when ANY of:
    - content_md is under 500 chars
    - the page has navigation + footer but no clear body content
    - two labels are plausible and you can't decide between them
    - the page kind contradicts what the URL pattern suggests

  Use `medium` when:
    - content is present and the kind is plausible but signals are mixed
    - the page is a hybrid (e.g. README that is also a product landing page)

  Use `high` ONLY when:
    - the page has substantial body content (> 2000 chars)
    - the kind is unambiguous from structural signals (headings,
      shapes, content flow)

STEP 3 — Emit affordances tuned to the kind. Use closed shape vocabulary
(list | timeline | key-value | table | code | comments | citations | comparison).
For failure kinds (paywalled / error / empty / blocked), return empty
follow-up list and one shape describing the obstacle.

Common confusions to AVOID:
  - GitHub releases page → `changelog`, NOT `listing` (it's a versioned changelog)
  - README on a code repo → `readme`, NOT `package-page` (unless it IS a package landing)
  - Comment thread with a couple replies → `thread`, NOT `status`
  - JSON feed / structured data → `json-feed`, NOT `listing`

Respond with strict JSON:
{{
  "page_kind": "<label>",
  "page_kind_confidence": "<low|medium|high>",
  "reasoning": "<one short sentence justifying the kind + confidence>",
  "answer": "<2-3 sentence answer; if page_kind is a failure kind, name the obstacle>",
  "follow_up_questions": ["<3-5 specific questions the page can actually answer; empty list if blocked/empty/error>"],
  "shapes": [
    {{"label": "...", "where": "...", "size": "..."}}
  ]
}}
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        body = text[3:]
        if body.startswith("json"):
            body = body[4:]
        if "```" in body:
            body = body.split("```", 1)[0]
        text = body.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "_raw": text[:400]}


async def _build_resources(s: AppSettings) -> tuple[Any, Any, Any]:
    sqlite = SqliteResource()
    state = build_state(
        settings=s,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(
            routes=cast("list[RouteRuleShape]", s.routes),
            proxies=cast("dict[str, ProxyEntryShape]", s.proxies),
        ),
        sqlite=sqlite,
    )
    browser_pool = build_browser_pool(settings=s)
    llm = build_llm_extractor(settings=s, sqlite=sqlite)
    return state, browser_pool, llm


async def _run(state: Any, browser_pool: Any, llm: Any, urls: list[tuple[str, str, str]], tag: str) -> None:
    from a2kit.testing import lazy

    provider = ClaudeCodeProvider()
    out_path = Path(f"eval/spikes/affordances_v4_{tag}_output.md")
    summary_path = Path(f"eval/spikes/affordances_v4_{tag}_summary.json")

    lines: list[str] = [
        f"# Affordances spike v4 — V_CTX_V2 calibration ({tag})\n",
        f"Primer ask: `{PRIMER_ASK}` · Model: claude-haiku-4-5\n",
        f"Corpus: {len(urls)} URLs\n\n",
    ]
    summary: dict[str, Any] = {"per_url": [], "totals": {"cost": 0.0, "ms": 0,
                                                          "fetch_failures": 0, "parse_failures": 0}}

    for idx, (slug, declared, url) in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] {slug}", flush=True)
        lines.append(f"\n---\n\n## {idx}. {slug} (declared: `{declared}`)\n\n`{url}`\n\n")
        per_url: dict[str, Any] = {"slug": slug, "declared_kind": declared, "url": url}

        try:
            resp = await fetch(
                url=url, ask=PRIMER_ASK, state=state,
                browser_pool=lazy(browser_pool), llm_extractor=lazy(llm),
            )
        except Exception as exc:
            lines.append(f"**FETCH RAISED**: `{exc}`\n")
            summary["totals"]["fetch_failures"] += 1
            per_url["fetch_status"] = f"raised: {exc!r}"
            summary["per_url"].append(per_url)
            continue

        content_md = resp.content_md or ""
        lines.append(f"**Fetch**: tier=`{resp.tier}` · status=`{resp.status or 'ok'}` · chars={len(content_md)}\n\n")
        per_url["fetch_status"] = resp.status or "ok"
        per_url["chars"] = len(content_md)

        if not content_md:
            lines.append("(no content_md)\n")
            summary["totals"]["fetch_failures"] += 1
            summary["per_url"].append(per_url)
            continue

        content_capped = content_md[:12000]
        t0 = time.perf_counter()
        response = await provider.complete(
            system=V_CTX_V2_SYSTEM,
            user=V_CTX_V2_TEMPLATE.format(
                content=content_capped,
                ask=PRIMER_ASK,
                n_chars=len(content_md),
            ),
            model="claude-haiku-4-5",
            max_tokens=1024,
            thinking_disabled=True,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        parsed = _parse_json(response.text)
        summary["totals"]["cost"] += response.cost_usd
        summary["totals"]["ms"] += elapsed
        if "_parse_error" in parsed:
            summary["totals"]["parse_failures"] += 1

        per_url["ctx_v2"] = {
            "cost": response.cost_usd,
            "ms": elapsed,
            "page_kind": parsed.get("page_kind"),
            "confidence": parsed.get("page_kind_confidence"),
            "reasoning": parsed.get("reasoning"),
            "shape_labels": [s.get("label") for s in parsed.get("shapes", []) if isinstance(s, dict)],
            "n_follow_ups": len(parsed.get("follow_up_questions", [])),
        }
        summary["per_url"].append(per_url)

        lines.append(
            f"**V_CTX_V2** · {elapsed} ms · ${response.cost_usd:.5f} · "
            f"kind=`{parsed.get('page_kind')}` ({parsed.get('page_kind_confidence')})\n\n```json\n"
            f"{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n"
        )

    t = summary["totals"]
    # Confidence distribution
    from collections import Counter
    conf_dist = Counter(u.get("ctx_v2", {}).get("confidence") for u in summary["per_url"] if "ctx_v2" in u)
    lines.append(
        f"\n---\n\n## Totals\n\n"
        f"- Cost: ${t['cost']:.4f} · time: {t['ms']/1000:.1f}s\n"
        f"- Fetch failures: {t['fetch_failures']} / {len(urls)}\n"
        f"- Parse failures: {t['parse_failures']}\n"
        f"- Confidence distribution: {dict(conf_dist)}\n"
    )
    out_path.write_text("\n".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Cost: ${t['cost']:.4f}  Confidence dist: {dict(conf_dist)}")


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context

    full = "--full" in sys.argv
    urls = URLS_FULL if full else [u for u in URLS_FULL if u[0] in WEAK_SLUGS]
    tag = "full" if full else "weak"

    s = AppSettings()
    state, browser_pool, llm = await _build_resources(s)
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        try:
            await _run(state, browser_pool, llm, urls, tag)
        finally:
            try:
                await state.sqlite.__aexit__(None, None, None)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
