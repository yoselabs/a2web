"""Spike — does `--bare` collapse the 26k preset overhead?

The 2026-05-23 probe found cache_read=26 822 identical across calls 2/3/4
regardless of page content. Hypothesis: that 26k is Claude Code's own
preset (CLAUDE.md auto-discovery, hooks, MCP, skills, auto-memory). The
CLI exposes `--bare` to strip all of that.

This spike re-runs the same 5-call plan via `claude_agent_sdk.query()`
with `extra_args={"bare": None}` and compares per-call totals against
the baseline probe. If `--bare` works as advertised:
  - prompt_tokens should drop by ~26k
  - the cache_read=26822 plateau on calls 2-4 should vanish
  - cost on call 1 should drop ~60%

Run:
    uv run python eval/spikes/claude_code_cache_bare.py
"""

from __future__ import annotations

import asyncio
import time

from a2web.packages.llm_extract import EXTRACT_CACHEABLE_V1
from a2web.packages.llm_extract.providers.base import extract_token_counts


_PAGE_A = """# The Lighthouse Keeper of Tristan da Cunha

Tristan da Cunha is the most remote inhabited archipelago in the world, sitting
some 2,400 kilometres west of Cape Town in the South Atlantic Ocean. Of its
several islands, only the eponymous main island is permanently populated, with
roughly 245 residents who share a small set of family names — Glass, Repetto,
Swain, Hagan, Green, Lavarello, Rogers — descended from the original 19th-century
settlers.

## Geography

The main island is a single composite volcano roughly 12 km across, rising
abruptly from the sea to a 2,062 m peak. The settlement of Edinburgh of the
Seven Seas occupies a narrow strip of flat ground on the north coast.

The climate is cool-temperate maritime, with mean annual temperature around
14°C and high rainfall year-round. Winds reach gale force frequently; the
landing beach at Edinburgh is workable on roughly 60 days per year.

## Notable events

In October 1961, an eruption of the previously-quiescent main volcano forced
the evacuation of the entire population to the UK via Cape Town. The
islanders lived in temporary accommodation in Calshot, Hampshire for nearly
two years before voting overwhelmingly to return; most of the population was
back on Tristan by the end of 1963.
"""

_PAGE_B = """# Coffee Cultivation in the Western Highlands of Guatemala

The departments of Huehuetenango, San Marcos, and Quetzaltenango together
account for the majority of Guatemala's specialty arabica output. Altitudes
between 1,500 and 2,000 metres, volcanic soils, and a sharp dry season produce
beans favoured by third-wave roasters in North America and Europe.
"""


async def _one_call(model: str, page: str, ask: str, *, bare: bool) -> dict:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        ThinkingConfigDisabled,
        query,
    )

    parts = EXTRACT_CACHEABLE_V1.render(content=page, ask=ask)
    system_str = "\n\n".join(EXTRACT_CACHEABLE_V1.system)
    prompt_str = parts.cache_prefix + parts.tail

    kwargs = {
        "model": model,
        "tools": [],
        "max_turns": 1,
        "max_thinking_tokens": 0,
        "system_prompt": system_str,
        "thinking": ThinkingConfigDisabled(type="disabled"),
    }
    if bare:
        # `--bare` requires ANTHROPIC_API_KEY (OAuth/keychain disabled). Use
        # narrower opt-outs that work with the OAuth session: skip settings
        # sources (CLAUDE.md auto-discovery), skills, plugins; tools already [].
        kwargs["setting_sources"] = []
        kwargs["skills"] = []
        kwargs["extra_args"] = {"disable-slash-commands": None}

    options = ClaudeAgentOptions(**kwargs)

    t0 = time.perf_counter()
    text_parts: list[str] = []
    result_msg = None
    async for msg in query(prompt=prompt_str, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
        elif isinstance(msg, ResultMessage):
            result_msg = msg
    elapsed = int((time.perf_counter() - t0) * 1000)

    prompt_t, completion_t, cache_create, cache_read = (0, 0, 0, 0)
    cost = 0.0
    if result_msg is not None:
        cost = float(result_msg.total_cost_usd or 0.0)
        prompt_t, completion_t, cache_create, cache_read = extract_token_counts(
            result_msg.usage or {}
        )
    return {
        "prompt_t": prompt_t,
        "cache_read": cache_read,
        "cache_create": cache_create,
        "completion_t": completion_t,
        "cost": cost,
        "ms": elapsed,
        "text_len": len("".join(text_parts)),
    }


async def main() -> None:
    model = "claude-haiku-4-5"
    plan = [
        ("call_1 A / Q1", _PAGE_A, "What is the population of Tristan da Cunha?"),
        ("call_2 A / Q2", _PAGE_A, "What is the climate like?"),
        ("call_3 B / Q2", _PAGE_B, "What is the climate like?"),
        ("call_4 A / Q3", _PAGE_A, "What happened in 1961?"),
        ("call_5 A / Q1", _PAGE_A, "What is the population of Tristan da Cunha?"),
    ]

    print("# Probe — `--bare` mode\n")
    print("Running 5 calls with extra_args={'bare': None}.\n")
    print("| call | prompt | cache_read | cache_create | ms | cost |")
    print("|------|-------:|-----------:|-------------:|---:|-----:|")
    bare_records = []
    for label, page, ask in plan:
        r = await _one_call(model, page, ask, bare=True)
        bare_records.append((label, r))
        print(
            f"| {label} | {r['prompt_t']} | {r['cache_read']} | {r['cache_create']} "
            f"| {r['ms']} | ${r['cost']:.5f} |"
        )
        await asyncio.sleep(0.2)

    print("\n## Comparison to baseline (2026-05-23 probe)\n")
    baseline = [41286, 41279, 40946, 41280, 41286]
    baseline_read = [0, 26822, 26822, 26822, 41284]
    print("| call | baseline prompt | bare prompt | Δ | baseline cache_read | bare cache_read |")
    print("|------|---------------:|-----------:|---:|-------------------:|----------------:|")
    for (label, r), b_prompt, b_read in zip(bare_records, baseline, baseline_read, strict=False):
        delta = r["prompt_t"] - b_prompt
        print(
            f"| {label} | {b_prompt} | {r['prompt_t']} | {delta:+d} | {b_read} | {r['cache_read']} |"
        )


if __name__ == "__main__":
    asyncio.run(main())
