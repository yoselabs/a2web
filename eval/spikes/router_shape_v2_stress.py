"""Spike v2 — three-way comparison on URLs that SHOULD force partial answers.

v1 showed that on easy URLs the router shape emits empty suggestion arrays and
costs ~32% less than the catalog shape. But it didn't test the risky behaviour:

  Does Haiku falsely claim `completeness: complete` when the answer is actually
  thin / partial? If yes, the silent-when-complete router is dangerous — the
  agent gets no fallback. A small always-on catalog might be safer.

Three prompts compared on 5 URLs designed to force partial answers:

  CATALOG   — v0.20-ish, always emits full payload (baseline)
  ROUTER    — silent when complete, suggests only when partial (v1)
  HYBRID    — always emits up-to-3 suggestions + a completeness flag so the
              agent can decide to ignore the catalog. Best of both?

URL picks (each designed to expose the partial-answer behaviour):

  arxiv-pdf-stub — fetched as HTML, real content is in the PDF. Asking about
                   the methodology should yield partial+suggest-PDF.
  hn-front-page  — listing. Asking about a specific post's discussion needs
                   try_url to the comments page.
  reddit-listing — subreddit hot list. Asking about top comment thread needs
                   try_url to a specific thread.
  long-spec-deep — RFC spec; asking a very specific deep question may need
                   the agent to land on a different section / sub-RFC.
  paywall-nyt    — preview only. Should suggest archive or alternate source.

Run:
    uv run python eval/spikes/router_shape_v2_stress.py
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


# (slug, ask, url, what_a_good_answer_would_need)
URLS: list[tuple[str, str, str, str]] = [
    (
        "arxiv-pdf-stub",
        "what experimental setup did the authors use in section 4?",
        "https://arxiv.org/abs/2402.17753",
        "deep section content — likely only in the PDF",
    ),
    (
        "hn-front-page",
        "what is the top-voted comment on the #1 story right now?",
        "https://news.ycombinator.com/",
        "comments are not on this page — need the item permalink",
    ),
    (
        "reddit-rust-hot",
        "what is the most discussed objection in the top thread?",
        "https://www.reddit.com/r/rust/",
        "comments are in the thread page, not the listing",
    ),
    (
        "rfc-9110-deep",
        "what does the spec say about the 421 Misdirected Request status code's interaction with HTTP/2?",
        "https://datatracker.ietf.org/doc/html/rfc9110",
        "very specific section — may need to navigate within",
    ),
    (
        "paywall-nyt",
        "what did Biden say about Trump in this article?",
        "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html",
        "paywalled — body content unavailable",
    ),
]


# ---------------------------------------------------------------------------
# CATALOG (v0.20-ish) — always emit full payload
# ---------------------------------------------------------------------------

CATALOG_SYSTEM = (
    "You are an extraction helper. Answer the question, then emit a catalog "
    "of useful side-information: page typing, what other shapes of data this "
    "page holds, follow-up questions, and ranked next links. Output strict JSON."
)

CATALOG_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Output strict JSON:
{{
  "answer": "<2-3 sentence answer, or 'no answer found' if the page lacks it>",
  "page_kind": "<one of: listing | thread | reference | article | tutorial | changelog | code | qa | spec | news | blog | product | video | status | paywalled | other>",
  "shapes": [
    {{"label": "<list|timeline|key-value|table|code|comments|citations|comparison>",
      "where": "<where on the page>", "size": "<rough scale>"}}
  ],
  "follow_up_questions": ["<3-5 questions you could answer about THIS page>"],
  "next_links": [
    {{"url": "<URL present in the markdown above>",
      "anchor": "<anchor text>",
      "kind": "<drilldown | related | source>",
      "reason": "<one phrase ≤80 chars, question-conditioned>"}}
  ]
}}
"""

# ---------------------------------------------------------------------------
# ROUTER — silent when complete (v1)
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = (
    "You are a routing helper. You ANSWER the question if you can. "
    "If your answer is partial, weak, or incomplete, you suggest where the "
    "calling agent should ask next. Quality over completeness — fewer, better "
    "suggestions beat many weak ones. When your answer is complete, the "
    "suggestion arrays SHOULD be empty. Be HONEST about partiality — if the "
    "page does not actually contain the answer the question needs, say so and "
    "suggest where to go. Output strict JSON."
)

ROUTER_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Output strict JSON:
{{
  "answer": "<2-3 sentence answer; if you cannot answer, say so plainly>",
  "answer_completeness": "<complete | partial | none>",
  "ask_here": ["<≤3 questions you could ALSO answer about this URL>"],
  "try_url": [
    {{"url": "<URL present in the markdown above>",
      "reason": "<question-conditioned, ≤120 chars, WHY this URL likely has what's missing>"}}
  ]
}}
"""

# ---------------------------------------------------------------------------
# HYBRID — always emit small catalog + completeness flag
# ---------------------------------------------------------------------------

HYBRID_SYSTEM = (
    "You are an extraction helper. Answer the question. ALSO ALWAYS emit a "
    "small set of next-move suggestions (the calling agent will decide whether "
    "to use them based on your `answer_completeness` flag). Cap each list at 3. "
    "When the answer is complete, suggestions become optional context; when "
    "partial, they become essential. Output strict JSON."
)

HYBRID_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Always emit suggestions, even when your answer is complete (cap at 3 each):

  ask_here  — follow-up questions about THIS URL (different question, same page)
  try_url   — URLs to fetch and re-ask the SAME question. Each entry needs a
              question-conditioned `reason` (WHY this URL likely has what's
              missing, not what kind of URL it is).

Output strict JSON:
{{
  "answer": "<2-3 sentence answer; say so plainly if you cannot>",
  "answer_completeness": "<complete | partial | none>",
  "ask_here": ["<≤3 questions>"],
  "try_url": [
    {{"url": "<URL present in the markdown above>",
      "reason": "<question-conditioned, ≤120 chars>"}}
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


async def _call(provider: ClaudeCodeProvider, system: str, user: str) -> tuple[dict, float, int]:
    t0 = time.perf_counter()
    response = await provider.complete(
        system=system,
        user=user,
        model="claude-haiku-4-5",
        max_tokens=1024,
        thinking_disabled=True,
    )
    elapsed = int((time.perf_counter() - t0) * 1000)
    return _parse_json(response.text), response.cost_usd, elapsed


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context
    from a2kit.testing import lazy

    settings = AppSettings()
    state, browser_pool, llm = await _build_resources(settings)
    provider = ClaudeCodeProvider()

    ambient = ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)
    ambient.__enter__()

    out_path = Path("eval/spikes/router_shape_v2_stress_output.md")
    summary_path = Path("eval/spikes/router_shape_v2_stress_summary.json")

    lines: list[str] = [
        "# Router-shape spike v2 — stressed URLs · catalog vs router vs hybrid\n\n",
        "Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled\n\n",
        "Three prompts on the same fetch. URLs deliberately chosen to force partial answers.\n",
        "Key question: does Haiku correctly self-assess partiality, or does it falsely\n",
        "claim `completeness: complete` and starve the agent of suggestions?\n\n",
    ]
    summary: dict[str, Any] = {"per_url": [], "totals": {"catalog_cost": 0.0, "router_cost": 0.0, "hybrid_cost": 0.0}}

    try:
        for idx, (slug, ask, url, expected) in enumerate(URLS, 1):
            print(f"\n[{idx}/{len(URLS)}] {slug} — {ask}", flush=True)
            lines.append(f"\n---\n\n## {idx}. {slug}\n\n`{url}`\n\nQ: **{ask}**\n\n_expected gap_: {expected}\n\n")

            per_url: dict[str, Any] = {"slug": slug, "url": url, "ask": ask, "expected_gap": expected}

            try:
                resp = await fetch(
                    url=url,
                    ask=ask,
                    state=state,
                    browser_pool=lazy(browser_pool),
                    llm_extractor=lazy(llm),
                )
            except Exception as exc:
                lines.append(f"**FETCH RAISED**: `{exc}`\n")
                per_url["fetch_status"] = f"raised: {exc!r}"
                summary["per_url"].append(per_url)
                continue

            content_md = resp.content_md or ""
            lines.append(f"Fetch: tier=`{resp.tier}` · status=`{resp.status or 'ok'}` · chars={len(content_md)}\n\n")
            if not content_md:
                lines.append("(no content_md — skipping)\n")
                summary["per_url"].append(per_url)
                continue
            content_capped = content_md[:12000]

            # --- CATALOG ---
            cat_parsed, cat_cost, cat_ms = await _call(
                provider,
                CATALOG_SYSTEM,
                CATALOG_TEMPLATE.format(content=content_capped, ask=ask),
            )
            summary["totals"]["catalog_cost"] += cat_cost

            # --- ROUTER ---
            rtr_parsed, rtr_cost, rtr_ms = await _call(
                provider,
                ROUTER_SYSTEM,
                ROUTER_TEMPLATE.format(content=content_capped, ask=ask),
            )
            summary["totals"]["router_cost"] += rtr_cost

            # --- HYBRID ---
            hyb_parsed, hyb_cost, hyb_ms = await _call(
                provider,
                HYBRID_SYSTEM,
                HYBRID_TEMPLATE.format(content=content_capped, ask=ask),
            )
            summary["totals"]["hybrid_cost"] += hyb_cost

            per_url["catalog"] = {
                "cost": cat_cost,
                "ms": cat_ms,
                "answer": cat_parsed.get("answer"),
                "page_kind": cat_parsed.get("page_kind"),
                "n_shapes": len(cat_parsed.get("shapes", [])),
                "n_followups": len(cat_parsed.get("follow_up_questions", [])),
                "n_next_links": len(cat_parsed.get("next_links", [])),
            }
            per_url["router"] = {
                "cost": rtr_cost,
                "ms": rtr_ms,
                "answer": rtr_parsed.get("answer"),
                "completeness": rtr_parsed.get("answer_completeness"),
                "n_ask_here": len(rtr_parsed.get("ask_here", [])),
                "n_try_url": len(rtr_parsed.get("try_url", [])),
                "try_url_reasons": [t.get("reason") for t in rtr_parsed.get("try_url", []) if isinstance(t, dict)],
            }
            per_url["hybrid"] = {
                "cost": hyb_cost,
                "ms": hyb_ms,
                "answer": hyb_parsed.get("answer"),
                "completeness": hyb_parsed.get("answer_completeness"),
                "n_ask_here": len(hyb_parsed.get("ask_here", [])),
                "n_try_url": len(hyb_parsed.get("try_url", [])),
                "try_url_reasons": [t.get("reason") for t in hyb_parsed.get("try_url", []) if isinstance(t, dict)],
            }

            lines.append(
                f"### CATALOG · {cat_ms} ms · ${cat_cost:.5f}\n\n"
                f"```json\n{json.dumps(cat_parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                f"### ROUTER · {rtr_ms} ms · ${rtr_cost:.5f}\n\n"
                f"```json\n{json.dumps(rtr_parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                f"### HYBRID · {hyb_ms} ms · ${hyb_cost:.5f}\n\n"
                f"```json\n{json.dumps(hyb_parsed, indent=2, ensure_ascii=False)}\n```\n"
            )
            summary["per_url"].append(per_url)

    finally:
        ambient.__exit__(None, None, None)
        try:
            await state.sqlite.__aexit__(None, None, None)
        except Exception:
            pass

    out_path.write_text("".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nwrote {out_path}\nwrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
