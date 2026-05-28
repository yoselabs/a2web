"""Spike — broader surface eval: catalog (v0.20-like) vs refined (5 fields).

Goal: find surprises. Run the same 10 research-realistic URLs through both
prompts, compare answers, suggestion utility, shape correctness, JSON discipline,
and cost. Surface anything unexpected.

Refined surface (from this conversation):
  answer:    str
  page_kind: closed-enum structural label
  shape:     prose | records | key-value | code | table | mixed  ← NEW
  ask_here:  list[str] (≤5, non-obvious only)
  try_url:   list[{url, reason}] (≤5, Q-conditioned reason)

10 URLs picked for realistic research tasks across:
  - paper abs       (read a paper)
  - listing         (browse top X)
  - thread          (consensus / objection)
  - api ref         (lookup specific method)
  - spec            (deep spec question)
  - Q&A             (accepted answer)
  - readme          (install / quickstart)
  - changelog       (latest release)
  - encyclopedia    (factual lookup)
  - package         (latest version + deps)

Run:
    uv run python eval/spikes/surface_eval_v1.py
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
    ("paper-abs", "what does the paper claim in 2 sentences?", "https://arxiv.org/abs/2402.17753"),
    ("hn-front", "what are the top 3 most-discussed posts right now?", "https://news.ycombinator.com/"),
    ("hn-thread", "what is the most-upvoted criticism in this thread?", "https://news.ycombinator.com/item?id=39745700"),
    (
        "mdn-array",
        "how do you remove the last element of an array in javascript?",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array",
    ),
    ("rfc-9110-idempotent", "what does the spec say about idempotent methods?", "https://datatracker.ietf.org/doc/html/rfc9110"),
    ("so-yield", "what is the accepted answer?", "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python"),
    ("gh-httpx-readme", "how do I install httpx and make a basic GET request?", "https://github.com/encode/httpx"),
    ("pydantic-releases", "what changed in the latest pydantic release?", "https://github.com/pydantic/pydantic/releases"),
    ("wiki-rust", "when was rust 1.0 released and who created it?", "https://en.wikipedia.org/wiki/Rust_(programming_language)"),
    ("pypi-httpx", "what is the latest version of httpx and its main dependencies?", "https://pypi.org/project/httpx/"),
]


# ---------------------------------------------------------------------------
# CATALOG (v0.20-ish baseline)
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
  "answer": "<2-3 sentence answer, or 'no answer found'>",
  "page_kind": "<one of: listing | thread | reference | article | tutorial | changelog | code | qa | spec | news | blog | product | encyclopedia | package | profile | spec | paywalled | error | empty | other>",
  "shapes": [
    {{"label": "<list|timeline|key-value|table|code|comments|citations|comparison>",
      "where": "<where on the page>"}}
  ],
  "follow_up_questions": ["<3-5 questions about THIS page>"],
  "next_links": [
    {{"url": "<URL from the markdown above>",
      "anchor": "<anchor text>",
      "kind": "<drilldown | related | source>",
      "reason": "<one phrase, question-conditioned>"}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# REFINED — the 5-field surface from this conversation
# ---------------------------------------------------------------------------

REFINED_SYSTEM = (
    "You are an extraction helper. Answer the question, then emit a tight "
    "set of routing hints for the calling agent. Strict JSON. Be terse — "
    "fewer high-signal entries beat many obvious ones."
)

REFINED_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Emit STRICT JSON with exactly these fields:

  answer       — 2-3 sentences answering the question. If the page doesn't
                 contain the answer, say so plainly. If the question asks for
                 a list (top N stories, all methods, etc.), the answer field
                 IS the list, as compact markdown.

  page_kind    — structural label, one of:
                 listing | thread | reference | api-reference | tutorial |
                 article-short | article-long | changelog | code-snippet |
                 source-file | readme | qa | spec | filing | news-article |
                 blog-post | product-page | video-page | json-feed | marketing |
                 encyclopedia | package-page | pdf-stub | spa | profile | status |
                 paywalled | error | empty | blocked | other

  shape        — data shape of the answer-bearing content, one of:
                 prose | records | key-value | code | table | mixed

  ask_here     — ≤5 follow-up questions about THIS URL. Emit ONLY questions
                 whose answer requires reading the body — NOT obvious from the
                 title, headings, or byline. If no non-obvious follow-ups
                 exist, emit fewer or none. Empty array [] is fine.

  try_url      — ≤5 URLs the calling agent should fetch and re-ask the SAME
                 question with. Each `reason` must be question-conditioned
                 (WHY this URL likely has what's missing, ≤120 chars). If the
                 current page fully answers the question, emit [].
                 Good: "PDF of same paper — section 4 has the experiment setup"
                 Bad:  "PDF version"

Output strict JSON:
{{
  "answer": "...",
  "page_kind": "...",
  "shape": "...",
  "ask_here": [],
  "try_url": [{{"url": "...", "reason": "..."}}]
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


def _heuristics(catalog: dict, refined: dict) -> dict:
    """Quick post-hoc heuristics on each side's output."""
    h: dict[str, Any] = {}

    cat_followups = catalog.get("follow_up_questions", []) or []
    ref_ask_here = refined.get("ask_here", []) or []

    # Obvious-filler detector: contains "what is the title", "who is the author",
    # "when was this published", "what are the main sections"
    obvious_patterns = [
        "title",
        "author",
        "publish",
        "main section",
        "what is this",
        "what is the article about",
        "what is the page about",
        "byline",
    ]

    def _obvious_count(qs: list) -> int:
        n = 0
        for q in qs:
            if not isinstance(q, str):
                continue
            lower = q.lower()
            if any(p in lower for p in obvious_patterns):
                n += 1
        return n

    h["catalog_followups_n"] = len(cat_followups)
    h["catalog_followups_obvious_n"] = _obvious_count(cat_followups)
    h["refined_ask_here_n"] = len(ref_ask_here)
    h["refined_ask_here_obvious_n"] = _obvious_count(ref_ask_here)

    h["catalog_next_links_n"] = len(catalog.get("next_links", []) or [])
    h["refined_try_url_n"] = len(refined.get("try_url", []) or [])

    h["catalog_shapes_n"] = len(catalog.get("shapes", []) or [])
    h["refined_shape"] = refined.get("shape")
    h["refined_page_kind"] = refined.get("page_kind")
    h["catalog_page_kind"] = catalog.get("page_kind")

    h["catalog_parse_fail"] = "_parse_error" in catalog
    h["refined_parse_fail"] = "_parse_error" in refined

    h["catalog_answer_len"] = len(catalog.get("answer", "") or "")
    h["refined_answer_len"] = len(refined.get("answer", "") or "")

    return h


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context
    from a2kit.testing import lazy

    settings = AppSettings()
    state, browser_pool, llm = await _build_resources(settings)
    provider = ClaudeCodeProvider()

    ambient = ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)
    ambient.__enter__()

    out_path = Path("eval/spikes/surface_eval_v1_output.md")
    summary_path = Path("eval/spikes/surface_eval_v1_summary.json")

    lines: list[str] = [
        "# Surface eval v1 — catalog vs refined (5 fields)\n\n",
        "Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled\n\n",
        "Two prompts on the same fetch. 10 research-realistic URLs.\n",
        "Refined surface: answer + page_kind + shape + ask_here(≤5,non-obvious) + try_url(≤5,Q-cond).\n\n",
    ]
    summary: dict[str, Any] = {
        "per_url": [],
        "totals": {"catalog_cost": 0.0, "refined_cost": 0.0, "catalog_parse_fails": 0, "refined_parse_fails": 0},
    }

    try:
        for idx, (slug, ask, url) in enumerate(URLS, 1):
            print(f"\n[{idx}/{len(URLS)}] {slug}", flush=True)
            lines.append(f"\n---\n\n## {idx}. {slug}\n\n`{url}`\n\nQ: **{ask}**\n\n")

            per_url: dict[str, Any] = {"slug": slug, "url": url, "ask": ask}

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
                per_url["fetch_status"] = resp.status or "ok"
                per_url["chars"] = 0
                summary["per_url"].append(per_url)
                continue
            content_capped = content_md[:12000]

            cat_parsed, cat_cost, cat_ms = await _call(
                provider,
                CATALOG_SYSTEM,
                CATALOG_TEMPLATE.format(content=content_capped, ask=ask),
            )
            ref_parsed, ref_cost, ref_ms = await _call(
                provider,
                REFINED_SYSTEM,
                REFINED_TEMPLATE.format(content=content_capped, ask=ask),
            )
            summary["totals"]["catalog_cost"] += cat_cost
            summary["totals"]["refined_cost"] += ref_cost

            h = _heuristics(cat_parsed, ref_parsed)
            if h["catalog_parse_fail"]:
                summary["totals"]["catalog_parse_fails"] += 1
            if h["refined_parse_fail"]:
                summary["totals"]["refined_parse_fails"] += 1

            per_url["fetch_status"] = resp.status or "ok"
            per_url["chars"] = len(content_md)
            per_url["catalog"] = {
                "cost": cat_cost,
                "ms": cat_ms,
                "answer": cat_parsed.get("answer"),
                "heuristics": {k: v for k, v in h.items() if k.startswith("catalog_")},
            }
            per_url["refined"] = {
                "cost": ref_cost,
                "ms": ref_ms,
                "answer": ref_parsed.get("answer"),
                "shape": ref_parsed.get("shape"),
                "page_kind": ref_parsed.get("page_kind"),
                "heuristics": {k: v for k, v in h.items() if k.startswith("refined_")},
            }

            lines.append(
                f"Fetch chars={len(content_md)}\n\n"
                f"### CATALOG · {cat_ms} ms · ${cat_cost:.5f}\n"
                f"_heuristics_: followups={h['catalog_followups_n']} "
                f"(obvious={h['catalog_followups_obvious_n']}), "
                f"next_links={h['catalog_next_links_n']}, "
                f"shapes={h['catalog_shapes_n']}, "
                f"page_kind=`{h['catalog_page_kind']}`"
                + (" · PARSE-FAIL" if h["catalog_parse_fail"] else "")
                + f"\n\n```json\n{json.dumps(cat_parsed, indent=2, ensure_ascii=False)}\n```\n\n"
                f"### REFINED · {ref_ms} ms · ${ref_cost:.5f}\n"
                f"_heuristics_: ask_here={h['refined_ask_here_n']} "
                f"(obvious={h['refined_ask_here_obvious_n']}), "
                f"try_url={h['refined_try_url_n']}, "
                f"page_kind=`{h['refined_page_kind']}`, "
                f"shape=`{h['refined_shape']}`"
                + (" · PARSE-FAIL" if h["refined_parse_fail"] else "")
                + f"\n\n```json\n{json.dumps(ref_parsed, indent=2, ensure_ascii=False)}\n```\n"
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
