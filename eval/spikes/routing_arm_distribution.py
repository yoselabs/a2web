"""Spike — how often does routing actually degrade, and does `index_lost` fire?

`fix-extraction-signal-fidelity` split the old `routing_lost: bool` into a
four-arm `RoutingOutcome`, and `ask-response` added an `index_lost` operator
hint on the two arms that cost the caller its index. Both shipped on offline
tests only: `test_index_loss_hint.py` proves the hint fires under CONSTRUCTED
conditions, and nothing measured how often those conditions occur on real pages.

That gap has a specific, already-paid-for failure mode. Five `DEFAULT`-tolerance
fields fired an `llm_wobble` on every healthy extraction until this session, and
the result was not an over-warning anyone triaged — it was `llm_wobble` ceasing
to mean anything at all. If `unclassified` is common in the wild, `index_lost`
becomes a warning on a large share of fetches and dies the same death, one layer
up.

**What this measures**, per corpus URL, on the real `query` path:

  * which `RoutingOutcome` arm the extraction landed in;
  * whether the `index_lost` hint fired;
  * whether the caller actually got an index (`also_here` / `other_pages`);
  * the terminal `status`, so a routing arm is never read without knowing
    whether retrieval itself succeeded.

**Cost posture (ADR-0016).** Subscription only: resolves `claude-code-sdk` and
wraps it in the shelf cost guard, so a metered pair raises `CostViolation`
BEFORE any spend. If no subscription backend resolves, this exits loudly rather
than falling through to metered billing — that fall-through is the $20
regression the ADR exists to prevent.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/routing_arm_distribution.py [N]
"""

from __future__ import annotations

import asyncio
import collections
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from a2web.components import build_components
from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.settings import AppSettings

_CORPUS = Path(__file__).resolve().parents[1] / "corpus.yaml"
_OUT = Path(__file__).resolve().parent / "routing_arm_distribution_summary.json"

#: Classes worth sampling. `gated` is included deliberately but sparsely — a
#: wall exercises the terminal path, and a routing arm read without knowing
#: whether retrieval succeeded is uninterpretable.
_CLASS_BUDGET = {"listing": 4, "affordance": 3, "clean": 3, "comments": 2, "article": 1, "spa": 1, "gated": 1}


def _sample() -> list[dict[str, Any]]:
    urls = yaml.safe_load(_CORPUS.read_text())["urls"]
    taken: collections.Counter[str] = collections.Counter()
    out = []
    for case in urls:
        cls = case.get("class", "?")
        if taken[cls] >= _CLASS_BUDGET.get(cls, 0) or not case.get("task"):
            continue
        taken[cls] += 1
        out.append(case)
    return out


async def _probe(parts: Any, case: dict[str, Any]) -> dict[str, Any]:
    response = await fetch(
        case["url"],
        ask=case["task"],
        state=await parts.state(),
        llm_extractor=parts.llm_extractor,
        browser_backend=parts.browser_backend,
        browser_robust_backend=parts.browser_robust_backend,
        cookie_jar=parts.cookie_jar,
    )
    ask = build_ask_response(response, include_content=False, debug=False)
    hints = [h.code for h in (ask.operator_hints or [])]
    return {
        "slug": case.get("slug") or case["url"],
        "class": case.get("class"),
        "status": ask.status or "ok",
        "routing_outcome": getattr(response, "_routing_outcome", None) and str(response._routing_outcome.value),
        "index_lost": "index_lost" in hints,
        "also_here": len(ask.also_here or ()),
        "other_pages": len(ask.other_pages or ()),
        "hints": hints,
    }


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 99
    cases = _sample()[:limit]
    parts = build_components(settings=AppSettings())
    rows: list[dict[str, Any]] = []
    try:
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case['url'][:70]}", flush=True)
            try:
                row = await _probe(parts, case)
            except Exception as exc:  # a spike reports failures, it does not hide them
                row = {"slug": case.get("slug"), "class": case.get("class"), "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            print(f"      -> {json.dumps({k: v for k, v in row.items() if k != 'slug'})}", flush=True)
    finally:
        await parts.aclose()

    arms = collections.Counter(r.get("routing_outcome") or ("ERROR" if "error" in r else "none") for r in rows)
    fired = sum(1 for r in rows if r.get("index_lost"))
    indexed = sum(1 for r in rows if (r.get("also_here") or 0) + (r.get("other_pages") or 0) > 0)
    summary = {
        "n": len(rows),
        "routing_arms": dict(arms),
        "index_lost_fired": fired,
        "index_lost_rate": round(fired / max(1, len(rows)), 3),
        "carried_an_index": indexed,
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))
    print("\n=== summary ===")
    print(f"  n                 : {len(rows)}")
    print(f"  routing arms      : {dict(arms)}")
    print(f"  index_lost fired  : {fired}/{len(rows)}  ({summary['index_lost_rate']:.0%})")
    print(f"  carried an index  : {indexed}/{len(rows)}")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
