"""Spike v2 — affordances at scale, with a context-aware prompt variant.

Builds on `affordances_v1.py` (5 URLs, single generic prompt). v2 widens to
30 URLs spanning content-type extremes (tiny / huge / structured / hostile /
dynamic / listing / comments / docs / media / forums / code) and runs TWO
prompt variants per URL:

  - V_GEN: the v1 generic prompt
  - V_CTX: context-aware — model first classifies page_kind, then proposes
           shapes/follow-ups tuned to that kind

Per-URL we measure: cost, latency, parse success, shape labels, follow-up
question density. The artefact is a per-URL side-by-side dump for hand
review — the spike is about *quality of judgement under different prompts*,
not pass/fail tests.

Run:
    uv run python eval/spikes/affordances_v2.py

Outputs:
    eval/spikes/affordances_v2_output.md         per-URL side-by-side
    eval/spikes/affordances_v2_summary.json      machine-readable totals
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


# 30-URL corpus spanning content-type extremes. Goal: find places where the
# generic prompt produces slop and a context-aware variant does better — and
# places where the extra classification step is wasted ceremony.
URLS: list[tuple[str, str, str]] = [
    # --- TINY ---
    ("tiny-arxiv",          "article-short", "https://arxiv.org/abs/2402.17753"),
    ("tiny-gh-gist",        "code-snippet",  "https://gist.github.com/jboner/2841832"),
    ("tiny-status-page",    "status",        "https://status.openai.com/"),
    # --- HUGE ---
    ("huge-wikipedia",      "encyclopedia",  "https://en.wikipedia.org/wiki/Rust_(programming_language)"),
    ("huge-mdn-array",      "api-reference", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array"),
    ("huge-changelog",      "changelog",     "https://github.com/pydantic/pydantic/releases"),
    # --- LISTING ---
    ("listing-hn",          "listing",       "https://news.ycombinator.com/"),
    ("listing-lobste",      "listing",       "https://lobste.rs/active"),
    ("listing-gh-trending", "listing",       "https://github.com/trending/python?since=daily"),
    ("listing-pypi",        "package-page",  "https://pypi.org/project/httpx/"),
    # --- COMMENTS ---
    ("comments-hn-item",    "threaded",      "https://news.ycombinator.com/item?id=39745700"),
    ("comments-lobste",     "threaded",      "https://lobste.rs/s/n1gytv"),
    # --- DOCS ---
    ("docs-fastapi",        "tutorial",      "https://fastapi.tiangolo.com/tutorial/first-steps/"),
    ("docs-postgres",       "api-reference", "https://www.postgresql.org/docs/current/sql-select.html"),
    ("docs-anthropic",      "api-reference", "https://docs.claude.com/en/api/messages"),
    # --- REFERENCE ---
    ("ref-rfc",             "spec",          "https://datatracker.ietf.org/doc/html/rfc9110"),
    ("ref-mdn-fetch",       "api-reference", "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API"),
    # --- NEWS / BLOG ---
    ("news-bbc",            "news-article",  "https://www.bbc.com/news/articles/cjwp82ye4y3o"),
    ("blog-julia-evans",    "blog-post",     "https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/"),
    # --- SOCIAL / FORUM ---
    ("forum-so-question",   "qa",            "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python"),
    # --- CODE ---
    ("code-gh-file",        "source-file",   "https://github.com/pydantic/pydantic/blob/main/pydantic/main.py"),
    ("code-gh-readme",      "readme",        "https://github.com/encode/httpx"),
    # --- PRODUCT / E-COMMERCE ---
    ("product-amazon",      "product-page",  "https://www.amazon.com/dp/B0BSHF7WHW"),
    # --- MEDIA ---
    ("media-yt-video",      "video-page",    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    # --- GOV / STRUCTURED RECORDS ---
    ("gov-sec-filing",      "filing",        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=10-K&dateb=&owner=include&count=40"),
    # --- SPA / DYNAMIC ---
    ("spa-react-dev",       "spa",           "https://react.dev/learn"),
    # --- DATA / JSON / RAW ---
    ("data-json-feed",      "json-feed",     "https://hnrss.org/frontpage.jsonfeed"),
    # --- HOSTILE / GATED ---
    ("gated-nyt",           "paywalled",     "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html"),
    # --- RESEARCH PAPER FULL ---
    ("paper-arxiv-pdf-stub","pdf-stub",      "https://arxiv.org/pdf/2402.17753"),
    # --- BUSINESS DOCS ---
    ("docs-cf-page",        "marketing",     "https://www.cloudflare.com/products/registrar/"),
]

PRIMER_ASK = "Give a 2-3 sentence summary of what this page is."

# --- Prompt V_GEN (v1 reproduction, with missed_sections dropped per v1 findings) ---
V_GEN_SYSTEM = (
    "You are an extraction helper. After answering the user's question about a web page, "
    "you also emit machine-readable affordances describing what ELSE the page contains. "
    "Be concrete; reference real structural features. Output strict JSON only."
)

V_GEN_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Respond with strict JSON of shape:
{{
  "answer": "<answer to primary question, 2-3 sentences>",
  "follow_up_questions": ["<3-5 specific questions a curious reader would plausibly ask next>"],
  "shapes": [
    {{"label": "<one of: list | timeline | key-value | table | code | comments | citations | comparison>",
      "where": "<short pointer e.g. 'top of page', 'under #Installation'>",
      "size": "<approximate count or small/medium/large>"}}
  ]
}}
"""

# --- Prompt V_CTX (context-aware: classify first, then tailor) ---
V_CTX_SYSTEM = (
    "You are an extraction helper. After answering the user's question, you classify "
    "the page's TYPE and then emit affordances TUNED to that type. A 'listing' page "
    "should propose drilldown questions; a 'reference' page should propose narrower "
    "lookup questions; a 'thread' page should propose questions about specific replies "
    "or the consensus; a 'paywalled' page should be honest about being blocked. "
    "Only propose follow-ups the page can actually answer. Output strict JSON only."
)

V_CTX_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Step 1 — classify the page. Pick the ONE best `page_kind` label from this closed set:
  listing | thread | reference | api-reference | tutorial | article-short | article-long |
  changelog | code-snippet | source-file | readme | qa | spec | filing | news-article |
  blog-post | product-page | video-page | json-feed | marketing | paywalled | status |
  encyclopedia | package-page | pdf-stub | spa | other

Step 2 — emit affordances tuned to that kind. Use the closed shape vocabulary
(list | timeline | key-value | table | code | comments | citations | comparison).
For paywalled / blocked / empty pages, be explicit (`page_kind="paywalled"`, empty
follow-ups, single shape describing the block).

Respond with strict JSON of shape:
{{
  "page_kind": "<label>",
  "page_kind_confidence": "<low|medium|high>",
  "answer": "<answer to primary question, 2-3 sentences; for blocked pages, say so>",
  "follow_up_questions": ["<3-5 specific questions the page can actually answer, tuned to page_kind>"],
  "shapes": [
    {{"label": "...", "where": "...", "size": "..."}}
  ]
}}
"""


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


async def _call(provider: ClaudeCodeProvider, system: str, prompt: str, model: str) -> dict:
    t0 = time.perf_counter()
    response = await provider.complete(
        system=system, user=prompt, model=model, max_tokens=1024, thinking_disabled=True,
    )
    elapsed = int((time.perf_counter() - t0) * 1000)
    parsed = _parse_json(response.text)
    return {
        "elapsed_ms": elapsed,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "cost_usd": response.cost_usd,
        "parsed": parsed,
    }


async def _run_corpus(state: Any, browser_pool: Any, llm: Any) -> None:
    from a2kit.testing import lazy

    provider = ClaudeCodeProvider()
    out_path = Path("eval/spikes/affordances_v2_output.md")
    summary_path = Path("eval/spikes/affordances_v2_summary.json")
    lines: list[str] = [
        "# Affordances spike v2 — generic vs context-aware\n",
        f"Primer ask: `{PRIMER_ASK}` · Model: claude-haiku-4-5 (post v0.20 opt-outs)\n",
        f"Corpus: {len(URLS)} URLs across content-type extremes\n\n",
    ]

    summary: dict[str, Any] = {"per_url": [], "totals": {"gen_cost": 0.0, "ctx_cost": 0.0,
                                                          "gen_ms": 0, "ctx_ms": 0,
                                                          "fetch_failures": 0}}

    for idx, (slug, declared_kind, url) in enumerate(URLS, 1):
        print(f"\n[{idx}/{len(URLS)}] {slug} ({declared_kind}) — {url}", flush=True)
        lines.append(f"\n---\n\n## {idx}. {slug} (declared: `{declared_kind}`)\n\n`{url}`\n\n")

        per_url: dict[str, Any] = {"slug": slug, "declared_kind": declared_kind, "url": url}

        # 1. Fetch via production orchestrator
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
        tier = resp.tier
        lines.append(f"**Fetch**: tier=`{tier}` · status=`{fetch_status}` · chars={len(content_md)}\n\n")
        per_url["fetch_status"] = fetch_status
        per_url["tier"] = tier
        per_url["chars"] = len(content_md)

        if not content_md:
            lines.append("(no content_md — skipping affordances)\n")
            summary["totals"]["fetch_failures"] += 1
            summary["per_url"].append(per_url)
            continue

        # Truncate to keep cost predictable (~12k chars ≈ ~3k tokens of content)
        content_capped = content_md[:12000]

        # 2. V_GEN
        v_gen = await _call(
            provider,
            V_GEN_SYSTEM,
            V_GEN_TEMPLATE.format(content=content_capped, ask=PRIMER_ASK),
            model="claude-haiku-4-5",
        )
        summary["totals"]["gen_cost"] += v_gen["cost_usd"]
        summary["totals"]["gen_ms"] += v_gen["elapsed_ms"]
        per_url["gen"] = {
            "cost": v_gen["cost_usd"], "ms": v_gen["elapsed_ms"],
            "parsed_ok": "_parse_error" not in v_gen["parsed"],
            "shape_labels": [s.get("label") for s in v_gen["parsed"].get("shapes", []) if isinstance(s, dict)],
            "n_follow_ups": len(v_gen["parsed"].get("follow_up_questions", [])),
        }

        # 3. V_CTX
        v_ctx = await _call(
            provider,
            V_CTX_SYSTEM,
            V_CTX_TEMPLATE.format(content=content_capped, ask=PRIMER_ASK),
            model="claude-haiku-4-5",
        )
        summary["totals"]["ctx_cost"] += v_ctx["cost_usd"]
        summary["totals"]["ctx_ms"] += v_ctx["elapsed_ms"]
        per_url["ctx"] = {
            "cost": v_ctx["cost_usd"], "ms": v_ctx["elapsed_ms"],
            "parsed_ok": "_parse_error" not in v_ctx["parsed"],
            "page_kind": v_ctx["parsed"].get("page_kind"),
            "page_kind_confidence": v_ctx["parsed"].get("page_kind_confidence"),
            "shape_labels": [s.get("label") for s in v_ctx["parsed"].get("shapes", []) if isinstance(s, dict)],
            "n_follow_ups": len(v_ctx["parsed"].get("follow_up_questions", [])),
        }

        summary["per_url"].append(per_url)

        # 4. Dump side-by-side
        lines.append(
            f"**V_GEN** · {v_gen['elapsed_ms']} ms · ${v_gen['cost_usd']:.5f} · "
            f"{v_gen['prompt_tokens']}p+{v_gen['completion_tokens']}c\n\n```json\n"
            f"{json.dumps(v_gen['parsed'], indent=2, ensure_ascii=False)}\n```\n\n"
        )
        lines.append(
            f"**V_CTX** · {v_ctx['elapsed_ms']} ms · ${v_ctx['cost_usd']:.5f} · "
            f"{v_ctx['prompt_tokens']}p+{v_ctx['completion_tokens']}c · "
            f"classified=`{v_ctx['parsed'].get('page_kind')}` ({v_ctx['parsed'].get('page_kind_confidence')})\n\n```json\n"
            f"{json.dumps(v_ctx['parsed'], indent=2, ensure_ascii=False)}\n```\n"
        )

    t = summary["totals"]
    lines.append(
        f"\n---\n\n## Totals\n\n"
        f"- V_GEN: ${t['gen_cost']:.4f} total · {t['gen_ms']/1000:.1f}s total\n"
        f"- V_CTX: ${t['ctx_cost']:.4f} total · {t['ctx_ms']/1000:.1f}s total\n"
        f"- Fetch failures: {t['fetch_failures']} / {len(URLS)}\n"
    )

    out_path.write_text("\n".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Wrote {summary_path}")
    print(f"V_GEN total: ${t['gen_cost']:.4f}  V_CTX total: ${t['ctx_cost']:.4f}")


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context

    s = AppSettings()
    state, browser_pool, llm = await _build_resources(s)
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        try:
            await _run_corpus(state, browser_pool, llm)
        finally:
            try:
                await state.sqlite.__aexit__(None, None, None)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
