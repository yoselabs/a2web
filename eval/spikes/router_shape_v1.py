"""Spike — router-shape vs catalog-shape (v0.20 affordances+next_links).

Question: when a2web treats itself as a ROUTER (hand the agent ONE good
next-ask, not a menu), is the output meaningfully better than v0.20's
catalog of affordances + next_links?

Two prompts, same Haiku call, same corpus of 4 URLs picked to stress the
distinction:

  arxiv-abs       — singleton with a PDF alternate (router should suggest
                    the PDF for "deeper claim"; catalog buries it under
                    next_links or shapes)
  hn-item         — paired pattern (article URL + discussion URL; router
                    should pick whichever serves the asked Q)
  blog-w-cites    — long-form with external citations (router's try_url
                    should surface a primary source)
  status-page     — should yield empty/sparse arrays in router; v0.20 still
                    emits affordances for the typing-axis reasoning

Run:
    uv run python eval/spikes/router_shape_v1.py
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


URLS: list[tuple[str, str, str]] = [
    ("arxiv-abs",      "what does the paper claim?",
     "https://arxiv.org/abs/2402.17753"),
    ("hn-item",        "what is the top objection in the discussion?",
     "https://news.ycombinator.com/item?id=39745700"),
    ("blog-julia",     "what does the author conclude about tailwind?",
     "https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/"),
    ("status-openai",  "is the API up right now?",
     "https://status.openai.com/"),
]


# ---------------------------------------------------------------------------
# Prompt A — CATALOG (closely mirrors v0.20 production: affordances + next_links)
# ---------------------------------------------------------------------------

CATALOG_SYSTEM = (
    "You are an extraction helper. Answer the question, then emit a catalog "
    "of useful side-information: page typing, what other shapes of data "
    "this page holds, follow-up questions, and ranked next links. Output strict JSON."
)

CATALOG_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Output strict JSON:
{{
  "answer": "<2-3 sentence answer to primary question, or 'no answer found'>",
  "page_kind": "<one of: listing | thread | reference | article | tutorial | changelog | code | qa | spec | news | blog | product | video | status | other>",
  "page_kind_confidence": "<low | medium | high>",
  "content_value": "<low | medium | high>",
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
# Prompt B — ROUTER (a2web hands the agent ONE good next-ask, not a menu)
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = (
    "You are a routing helper. You ANSWER the question if you can. "
    "If your answer is partial, weak, or incomplete, you suggest where the "
    "calling agent should ask next. Quality over completeness — fewer, better "
    "suggestions beat many weak ones. When your answer is complete, the "
    "suggestion arrays SHOULD be empty. The downstream agent will fetch the "
    "suggested URL and re-ask the SAME question. Output strict JSON."
)

ROUTER_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Two slots for next-asks. Use them ONLY when your `answer` is incomplete:

  ask_here  — up to 3 follow-up questions the agent could ask about THIS URL.
              Use when the page has more content the primary question didn't
              touch but a slightly different question would unlock.

  try_url   — up to 3 URLs the agent should fetch and re-ask the SAME question
              with. Each entry must include a question-conditioned `reason`
              that tells the agent WHY this URL likely contains the answer
              the current page lacked (not what kind of URL it is).
              Examples of good reasons:
                "PDF of the same paper — claim is in section 4, omitted here"
                "discussion thread for the article above — likely has the objection"
                "primary source cited for the central statistic"
              Examples of BAD reasons:
                "PDF version"
                "comments"
                "related"

Output strict JSON:
{{
  "answer": "<2-3 sentence answer; if you cannot answer, say so plainly>",
  "answer_completeness": "<complete | partial | none>",
  "ask_here": ["<question phrased so the agent could ask THIS URL again>"],
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


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context
    from a2kit.testing import lazy

    settings = AppSettings()
    state, browser_pool, llm = await _build_resources(settings)
    provider = ClaudeCodeProvider()

    ambient = ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)
    ambient.__enter__()

    out_path = Path("eval/spikes/router_shape_v1_output.md")
    summary_path = Path("eval/spikes/router_shape_v1_summary.json")

    lines: list[str] = [
        "# Router-shape spike v1 — catalog vs router\n\n",
        "Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled\n\n",
        "Two prompts, same content_md, same question. Compared on:\n",
        "- did the suggestion arrays actually help follow up?\n",
        "- were reasons Q-conditioned?\n",
        "- did router emit empty arrays when its answer was complete?\n",
        "- token/cost delta\n\n",
    ]
    summary: dict[str, Any] = {"per_url": [], "totals": {"catalog_cost": 0.0, "router_cost": 0.0}}

    try:
        for idx, (slug, ask, url) in enumerate(URLS, 1):
            print(f"\n[{idx}/{len(URLS)}] {slug} — {ask}", flush=True)
            lines.append(f"\n---\n\n## {idx}. {slug}\n\n`{url}`\n\nQ: **{ask}**\n\n")

            per_url: dict[str, Any] = {"slug": slug, "url": url, "ask": ask}

            try:
                resp = await fetch(
                    url=url, ask=ask, state=state,
                    browser_pool=lazy(browser_pool), llm_extractor=lazy(llm),
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

            # ----- CATALOG -----
            t0 = time.perf_counter()
            cat_resp = await provider.complete(
                system=CATALOG_SYSTEM,
                user=CATALOG_TEMPLATE.format(content=content_capped, ask=ask),
                model="claude-haiku-4-5", max_tokens=1024, thinking_disabled=True,
            )
            cat_ms = int((time.perf_counter() - t0) * 1000)
            cat_parsed = _parse_json(cat_resp.text)
            summary["totals"]["catalog_cost"] += cat_resp.cost_usd

            # ----- ROUTER -----
            t0 = time.perf_counter()
            rtr_resp = await provider.complete(
                system=ROUTER_SYSTEM,
                user=ROUTER_TEMPLATE.format(content=content_capped, ask=ask),
                model="claude-haiku-4-5", max_tokens=1024, thinking_disabled=True,
            )
            rtr_ms = int((time.perf_counter() - t0) * 1000)
            rtr_parsed = _parse_json(rtr_resp.text)
            summary["totals"]["router_cost"] += rtr_resp.cost_usd

            per_url["catalog"] = {
                "cost": cat_resp.cost_usd, "ms": cat_ms,
                "answer": cat_parsed.get("answer"),
                "n_shapes": len(cat_parsed.get("shapes", [])),
                "n_followups": len(cat_parsed.get("follow_up_questions", [])),
                "n_next_links": len(cat_parsed.get("next_links", [])),
            }
            per_url["router"] = {
                "cost": rtr_resp.cost_usd, "ms": rtr_ms,
                "answer": rtr_parsed.get("answer"),
                "completeness": rtr_parsed.get("answer_completeness"),
                "n_ask_here": len(rtr_parsed.get("ask_here", [])),
                "n_try_url": len(rtr_parsed.get("try_url", [])),
            }

            lines.append(
                f"### CATALOG · {cat_ms} ms · ${cat_resp.cost_usd:.5f}\n\n"
                f"```json\n{json.dumps(cat_parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                f"### ROUTER · {rtr_ms} ms · ${rtr_resp.cost_usd:.5f}\n\n"
                f"```json\n{json.dumps(rtr_parsed, indent=2, ensure_ascii=False)}\n```\n"
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
