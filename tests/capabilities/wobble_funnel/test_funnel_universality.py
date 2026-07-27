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
from tests._helpers.log_capture import capture_logs


def _has_wobble(records: list[dict], boundary: str) -> bool:
    return any(r.get("event") == "llm_wobble" and r.get("boundary") == boundary for r in records)


def _healthy_router_envelope() -> str:
    """The minimal envelope a healthy extraction produces.

    Every optional field is absent, because the prompt tells the model to OMIT
    them: `obstacle` "OMIT on healthy pages", `other_pages` "If no '## page
    links' list is present, OMIT", `refinement_axes` / `item_total_seen` only
    on listings. This is the COMMON case, not a degraded one.
    """
    return json.dumps({"answer": "rust borrow checker", "structural_form": "reference", "shape": "prose"})


def test_healthy_router_envelope_emits_no_wobble_at_all() -> None:
    """A signal that fires on every healthy call is not a signal.

    This envelope used to emit FIVE `llm_wobble` warnings — one per legitimately
    omitted optional field — so `llm_wobble` fired on 100% of healthy
    extractions. It was found only because something tried to USE it as a
    measurement channel and discovered it could not detect anything. The five
    fields are now `OPTIONAL` rather than `DEFAULT`: absent-by-contract is not a
    recovery, so there is nothing to report.
    """
    with capture_logs() as records:
        answer, wobbled = _split_answer_and_routing(_healthy_router_envelope(), model="test-model")
    assert wobbled is not None
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert answer == "rust borrow checker"
    assert [r for r in records if r.get("event") == "llm_wobble"] == []


def test_malformed_optional_field_still_emits_a_wobble() -> None:
    """`OPTIONAL` silences ABSENCE, and must not silence CORRUPTION.

    The funnel's policies fire only on absent fields, so a field present with
    the wrong type never reaches them — a string where `also_here` should be a
    list is coerced to empty and the content is gone. That was survivable while
    every absence was reported; once absence is silent, this becomes the only
    remaining way for an index to disappear without a word.
    """
    raw = json.dumps({"answer": "a", "structural_form": "article", "shape": "prose", "also_here": "not a list"})
    with capture_logs() as records:
        _split_answer_and_routing(raw, model="test-model")
    fields = [r.get("field") for r in records if r.get("event") == "llm_wobble"]
    assert fields == ["also_here"]


def test_extractor_routing_still_emits_wobble_when_a_required_field_drops() -> None:
    """The other half: the boundary is still wired to the funnel.

    Silence on optional fields would be worthless if it were achieved by
    disconnecting the boundary. `structural_form` is `(required)` per the
    prompt, so dropping it is a real wobble and still reports.
    """
    raw = json.dumps({"answer": "rust borrow checker", "shape": "prose"})
    with capture_logs() as records:
        _answer, wobbled = _split_answer_and_routing(raw, model="test-model")
    assert wobbled is not None
    fields = {r.get("field") for r in records if r.get("event") == "llm_wobble"}
    assert "structural_form" in fields
    # ...and the optional neighbours stay silent even on this degraded call.
    assert fields.isdisjoint({"obstacle", "also_here", "other_pages", "refinement_axes", "item_total_seen"})


def test_extractor_next_links_emits_wobble_on_dropped_entries() -> None:
    body = '```next_links\n[{"anchor":"a","url":"u","reason":"r","kind":"drilldown"},{"anchor":"bad"}]\n```'
    with capture_logs() as records:
        _, links = _split_answer_and_next_links(body, model="test-model")
    assert len(links) == 1
    assert _has_wobble(records, "extractor.next_links")


def test_judge_funnel_returns_wobbled_with_reasoning_recovered() -> None:
    raw = json.dumps({"scores": [4, 5], "overall": 5, "reached": True})  # no reasoning
    with capture_logs() as records:
        wobbled = _funnel_verdict(raw, model="test-model")
    # Wobbled wraps _Parsed; runtime is identity (NewType). Spot-check it
    # has the private _Parsed shape (value + recovered_fields).
    assert hasattr(wobbled, "value")
    assert hasattr(wobbled, "recovered_fields")
    assert _has_wobble(records, "judge")


def test_bench_clarity_funnel_returns_wobbled() -> None:
    raw = json.dumps({"clarity": 4})  # no reasoning → DEFAULT recovery
    with capture_logs() as records:
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
    with capture_logs() as records:
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
