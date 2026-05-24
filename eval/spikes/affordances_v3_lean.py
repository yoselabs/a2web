"""Spike v3 — `V_LEAN` variant: affordances WITHOUT the answer field.

Hypothesis from v1 findings: in production, affordances fold into the existing
extraction call. The extractor already generates the answer; the affordances
addendum only needs to emit `shapes` + `follow_up_questions`. The v1 and v2
spikes have the model re-generate the answer redundantly, inflating completion
tokens.

v3 measures the lean shape directly: a single Haiku call that emits ONLY
affordances (no answer), against the same 30-URL corpus as v2. Together with
v2 this lets us compare three points:

  V_GEN  (v2): generic + answer
  V_CTX  (v2): context-classified + answer
  V_LEAN (v3): affordances only, no answer, no classification

Runs independently — fetches fresh content (the bench harness has no shared
content cache between runs). Different hosts so v2/v3 in parallel don't pile
on a single origin.

Run:
    uv run python eval/spikes/affordances_v3_lean.py

Outputs:
    eval/spikes/affordances_v3_lean_output.md
    eval/spikes/affordances_v3_lean_summary.json
"""

from __future__ import annotations

import asyncio
import json
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

# Same 30-URL corpus as v2 — duplicated (not imported) because eval/ is not on
# the Python path. Keep in sync with affordances_v2.py manually.
PRIMER_ASK = "Give a 2-3 sentence summary of what this page is."
URLS: list[tuple[str, str, str]] = [
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


V_LEAN_SYSTEM = (
    "You are an extraction helper. Your only job is to emit machine-readable affordances "
    "about a web page: structural shapes present, and follow-up questions the page can "
    "actually answer. You do NOT answer the user's primary question (it is handled "
    "separately). Be concrete. Output strict JSON only."
)

V_LEAN_TEMPLATE = """Web page content:
{content}

A separate extractor will answer this primary question: {ask}

Your job: emit affordances. Respond with strict JSON of shape:
{{
  "shapes": [
    {{"label": "<one of: list | timeline | key-value | table | code | comments | citations | comparison>",
      "where": "<short pointer e.g. 'top of page', 'under #Installation'>",
      "size": "<approximate count or small/medium/large>"}}
  ],
  "follow_up_questions": ["<3-5 specific questions the page can actually answer, distinct from the primary question>"]
}}

If the page is blocked / paywalled / empty, return empty lists for both.
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


async def _run(state: Any, browser_pool: Any, llm: Any) -> None:
    from a2kit.testing import lazy

    provider = ClaudeCodeProvider()
    out_path = Path("eval/spikes/affordances_v3_lean_output.md")
    summary_path = Path("eval/spikes/affordances_v3_lean_summary.json")
    lines: list[str] = [
        "# Affordances spike v3 — V_LEAN (no answer field)\n",
        f"Primer ask: `{PRIMER_ASK}` · Model: claude-haiku-4-5 (post v0.20 opt-outs)\n",
        f"Corpus: {len(URLS)} URLs (same as v2 for cross-comparison)\n\n",
    ]
    summary: dict[str, Any] = {"per_url": [], "totals": {"cost": 0.0, "ms": 0, "fetch_failures": 0,
                                                          "parse_failures": 0}}

    for idx, (slug, declared_kind, url) in enumerate(URLS, 1):
        print(f"\n[{idx}/{len(URLS)}] {slug} ({declared_kind})", flush=True)
        lines.append(f"\n---\n\n## {idx}. {slug} (declared: `{declared_kind}`)\n\n`{url}`\n\n")
        per_url: dict[str, Any] = {"slug": slug, "declared_kind": declared_kind, "url": url}

        try:
            resp = await fetch(
                url=url, ask=PRIMER_ASK, state=state,
                browser_pool=lazy(browser_pool), llm_extractor=lazy(llm),
            )
        except Exception as exc:
            print(f"  ! fetch raised: {exc}", flush=True)
            lines.append(f"**FETCH RAISED**: `{exc}`\n")
            summary["totals"]["fetch_failures"] += 1
            per_url["fetch_status"] = f"raised: {exc!r}"
            summary["per_url"].append(per_url)
            continue

        content_md = resp.content_md or ""
        fetch_status = resp.status or "ok"
        lines.append(f"**Fetch**: tier=`{resp.tier}` · status=`{fetch_status}` · chars={len(content_md)}\n\n")
        per_url["fetch_status"] = fetch_status
        per_url["tier"] = resp.tier
        per_url["chars"] = len(content_md)

        if not content_md:
            lines.append("(no content_md — skipping affordances)\n")
            summary["totals"]["fetch_failures"] += 1
            summary["per_url"].append(per_url)
            continue

        content_capped = content_md[:12000]
        t0 = time.perf_counter()
        response = await provider.complete(
            system=V_LEAN_SYSTEM,
            user=V_LEAN_TEMPLATE.format(content=content_capped, ask=PRIMER_ASK),
            model="claude-haiku-4-5",
            max_tokens=768,
            thinking_disabled=True,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        parsed = _parse_json(response.text)

        summary["totals"]["cost"] += response.cost_usd
        summary["totals"]["ms"] += elapsed
        if "_parse_error" in parsed:
            summary["totals"]["parse_failures"] += 1
        per_url["lean"] = {
            "cost": response.cost_usd,
            "ms": elapsed,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "parsed_ok": "_parse_error" not in parsed,
            "shape_labels": [s.get("label") for s in parsed.get("shapes", []) if isinstance(s, dict)],
            "n_follow_ups": len(parsed.get("follow_up_questions", [])),
        }
        summary["per_url"].append(per_url)

        lines.append(
            f"**V_LEAN** · {elapsed} ms · ${response.cost_usd:.5f} · "
            f"{response.prompt_tokens}p+{response.completion_tokens}c\n\n```json\n"
            f"{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n"
        )

    t = summary["totals"]
    lines.append(
        f"\n---\n\n## Totals\n\n"
        f"- V_LEAN: ${t['cost']:.4f} total · {t['ms']/1000:.1f}s total\n"
        f"- Fetch failures: {t['fetch_failures']} / {len(URLS)}\n"
        f"- Parse failures: {t['parse_failures']} / {len(URLS) - t['fetch_failures']}\n"
    )
    out_path.write_text("\n".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Wrote {summary_path}")
    print(f"V_LEAN total: ${t['cost']:.4f}")


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context

    s = AppSettings()
    state, browser_pool, llm = await _build_resources(s)
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        try:
            await _run(state, browser_pool, llm)
        finally:
            try:
                await state.sqlite.__aexit__(None, None, None)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
