"""Capability: every LLM-JSON site funnels through wobble.parse_with_policy.

Black-box check that each of the four canonical sites surfaces a `Wobbled`
return at its boundary and fires `llm_wobble` on optional-field misses. Hand
in a malformed-but-recoverable envelope, observe the recovery path.

Sites covered:
  - extractor._split_answer_and_routing  (router envelope, object shape)
  - extractor._split_answer_and_next_links (next_links block, list shape)
  - judge._funnel_verdict (judge verdict, object shape + permissive fallback)
  - bench_judge._funnel_two_field (clarity + next_links, object shape)

`fetcher_response._project_routing` is intentionally not in this list — it
does not call json.loads (per design D7); its `llm_wobble` emit comes from
pydantic closed-enum validation, exercised in test_router_wire.py.
"""

from __future__ import annotations

import json

from a2web.llm_eval.bench_judge import _funnel_two_field
from a2web.packages.llm_extract.extractor import (
    _split_answer_and_next_links,
    _split_answer_and_routing,
)
from a2web.packages.llm_extract.judge import _funnel_verdict
from a2web.packages.llm_extract.wobble import (
    BENCH_CLARITY_POLICY,
    BENCH_NEXT_LINKS_POLICY,
)
from tests._helpers.log_capture import capture_a2kit_logs


def _has_wobble(records: list[dict], boundary: str) -> bool:
    return any(r.get("event") == "llm_wobble" and r.get("boundary") == boundary for r in records)


def test_extractor_routing_emits_wobble_on_missing_genre() -> None:
    raw = json.dumps(
        {
            "answer": "rust borrow checker",
            "structural_form": "reference",
            "shape": "prose",
            # genre / obstacle / ask_here / try_url all missing → DEFAULT recovery
        }
    )
    with capture_a2kit_logs() as records:
        answer, wobbled = _split_answer_and_routing(raw, model="test-model")
    assert wobbled is not None
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert answer == "rust borrow checker"
    # all four optional fields wobbled
    fields = {r.get("field") for r in records if r.get("event") == "llm_wobble"}
    assert {"genre", "obstacle", "ask_here", "try_url"} <= fields


def test_extractor_next_links_emits_wobble_on_dropped_entries() -> None:
    body = '```next_links\n[{"anchor":"a","url":"u","reason":"r","kind":"drilldown"},{"anchor":"bad"}]\n```'
    with capture_a2kit_logs() as records:
        _, links = _split_answer_and_next_links(body, model="test-model")
    assert len(links) == 1
    assert _has_wobble(records, "extractor.next_links")


def test_judge_funnel_returns_wobbled_with_reasoning_recovered() -> None:
    raw = json.dumps({"scores": [4, 5], "overall": 5, "reached": True})  # no reasoning
    with capture_a2kit_logs() as records:
        wobbled = _funnel_verdict(raw, model="test-model")
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert _has_wobble(records, "judge")


def test_bench_clarity_funnel_returns_wobbled() -> None:
    raw = json.dumps({"clarity": 4})  # no reasoning → DEFAULT recovery
    with capture_a2kit_logs() as records:
        wobbled = _funnel_two_field(
            raw,
            score_field="clarity",
            boundary="bench_judge_clarity",
            policies=BENCH_CLARITY_POLICY,
            model="test-model",
        )
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert _has_wobble(records, "bench_judge_clarity")


def test_bench_next_links_funnel_returns_wobbled() -> None:
    raw = json.dumps({"next_links_score": 3})  # no reasoning
    with capture_a2kit_logs() as records:
        wobbled = _funnel_two_field(
            raw,
            score_field="next_links_score",
            boundary="bench_judge_next_links",
            policies=BENCH_NEXT_LINKS_POLICY,
            model="test-model",
        )
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert _has_wobble(records, "bench_judge_next_links")
