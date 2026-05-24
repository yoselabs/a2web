"""Spike — affordances on top of `ask`.

Hypothesis: when an agent calls `ask(url, question)`, the Haiku extraction
already touches the entire page — for ~$0 marginal cost it could emit, alongside
the answer:
  - follow_up_questions: 3-5 questions a curious reader would plausibly ask next
  - shapes:              data structures present on the page (timeline, list,
                         key-value, code, table, ...) that the agent could
                         re-extract with a more targeted ask
  - missed_sections:     section/heading labels the answer didn't touch

The cheap question: are these affordances *good enough* on a single-call augmented
prompt to be useful in production, or do they need a separate pass / specialised
prompt?

Method: 5 diverse corpus URLs → fetch via production orchestrator → call Haiku
with an affordance-augmented prompt → dump structured outputs for hand review.

Run:
    uv run python eval/spikes/affordances_v1.py
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast

from a2web.fetcher import fetch
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from a2web.packages.proxy_routing import ProxyPool, RouteRuleShape, ProxyEntryShape
from a2web.packages.browser_pool import BrowserPool
from a2web.settings import AppSettings
from a2web.state import build_state, SqliteResource
from a2web.server import build_browser_pool, build_llm_extractor
from purgatory import AsyncCircuitBreakerFactory


URLS: list[tuple[str, str]] = [
    ("hn-front",       "https://news.ycombinator.com/"),
    ("wikipedia-rust", "https://en.wikipedia.org/wiki/Rust_(programming_language)"),
    ("pypi-httpx",     "https://pypi.org/project/httpx/"),
    ("arxiv-abstract", "https://arxiv.org/abs/2402.17753"),
    ("reddit-comments", "https://www.reddit.com/r/LocalLLaMA/comments/1iqz5nb/"),
]

PRIMER_ASK = "Give a 2-3 sentence summary of what this page is."

AFFORDANCES_SYSTEM = (
    "You are an extraction helper. After answering the user's question about a web page, "
    "you also emit machine-readable affordances describing what ELSE the page contains. "
    "Be concrete; reference real structural features. Output strict JSON only, no prose."
)

AFFORDANCES_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Respond with strict JSON of shape:
{{
  "answer": "<answer to primary question, 2-3 sentences>",
  "follow_up_questions": ["<3-5 specific questions a curious reader would plausibly ask after seeing the answer>"],
  "shapes": [
    {{"label": "<one of: list | timeline | key-value | table | code | comments | citations | comparison>",
      "where": "<short pointer, e.g. 'top of page', 'under #Installation'>",
      "size": "<approximate count or 'small/medium/large'>"}}
  ],
  "missed_sections": ["<section/heading names the answer did not touch>"]
}}
"""


async def _build_resources(s: AppSettings) -> tuple[Any, Any, Any]:
    """Bare-bones build of (state, browser_pool, llm_extractor) for a spike."""
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


async def _run_affordances(content: str, ask: str, model: str = "claude-haiku-4-5") -> dict:
    provider = ClaudeCodeProvider()
    prompt = AFFORDANCES_TEMPLATE.format(content=content[:12000], ask=ask)
    t0 = time.perf_counter()
    response = await provider.complete(
        system=AFFORDANCES_SYSTEM,
        user=prompt,
        model=model,
        max_tokens=1024,
        thinking_disabled=True,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    text = response.text.strip()
    if text.startswith("```"):
        # tolerate ```json fences
        text = text.split("```")[1] if "```" in text[3:] else text
        if text.startswith("json"):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        parsed = {"parse_error": str(exc), "raw_text": response.text}
    return {
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "cost_usd": response.cost_usd,
        "parsed": parsed,
    }


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context

    s = AppSettings()
    state, browser_pool, llm = await _build_resources(s)

    # Phases inside fetch() emit via a2kit.ldd.event(...) which requires an
    # ambient ctx. Spike runs outside a tool dispatch so we wrap manually.
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        await _run_corpus(state, browser_pool, llm)


async def _run_corpus(state, browser_pool, llm) -> None:

    out_path = Path("eval/spikes/affordances_v1_output.md")
    lines: list[str] = ["# Affordances spike v1 — outputs\n",
                        f"Primer ask: `{PRIMER_ASK}`\n",
                        "Model: claude-haiku-4-5 via ClaudeCodeProvider (post v0.20 opt-outs)\n\n"]

    total_cost = 0.0
    for slug, url in URLS:
        print(f"\n=== {slug} ({url})", flush=True)
        lines.append(f"\n---\n\n## {slug} — {url}\n")

        try:
            from a2kit.testing import lazy
            resp = await fetch(
                url=url,
                ask=PRIMER_ASK,
                state=state,
                browser_pool=lazy(browser_pool),
                llm_extractor=lazy(llm),
            )
        except Exception as exc:
            print(f"  ! fetch failed: {exc}", flush=True)
            lines.append(f"**FETCH ERROR**: `{exc}`\n")
            continue

        content_md = resp.content_md or ""
        lines.append(f"**Fetch tier**: `{resp.tier}` · **chars**: {len(content_md)} · **status**: `{resp.status or 'ok'}`\n\n")
        if not content_md:
            lines.append("(no content_md returned)\n")
            continue

        affordances = await _run_affordances(content_md, PRIMER_ASK)
        total_cost += affordances["cost_usd"]
        lines.append(
            f"**Affordances call**: {affordances['elapsed_ms']} ms · "
            f"{affordances['prompt_tokens']} prompt + {affordances['completion_tokens']} completion · "
            f"${affordances['cost_usd']:.5f}\n\n"
        )
        lines.append("```json\n")
        lines.append(json.dumps(affordances["parsed"], indent=2, ensure_ascii=False))
        lines.append("\n```\n")

    lines.append(f"\n---\n\n**Total affordances cost across {len(URLS)} URLs**: ${total_cost:.4f}\n")

    out_path.write_text("\n".join(lines))
    print(f"\nWrote {out_path}")
    print(f"Total affordances cost: ${total_cost:.4f}")

    # graceful resource shutdown — best-effort
    try:
        await state.sqlite.__aexit__(None, None, None)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
