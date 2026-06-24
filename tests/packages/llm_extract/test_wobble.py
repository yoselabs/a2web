"""Unit tests for the shared LLM-contract wobble discipline."""

from __future__ import annotations

import pytest

from a2web.packages.llm_extract import (
    WobblePolicy,
    WobbleSkip,
    WobbleTolerance,
)
from a2web.packages.llm_extract.wobble import apply_policy
from tests._helpers.log_capture import capture_a2kit_logs


def _ctx(parsed: dict[str, object], field: str, policy: WobblePolicy) -> object:
    return apply_policy(
        parsed,
        field,
        policy,
        boundary="test",
        model="m",
        raw_excerpt="raw",
    )


def test_strict_present_returns_value() -> None:
    assert _ctx({"x": 5}, "x", WobblePolicy(WobbleTolerance.STRICT)) == 5


def test_strict_missing_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        _ctx({}, "x", WobblePolicy(WobbleTolerance.STRICT))


def test_derive_calls_callable_and_logs() -> None:
    policy = WobblePolicy(WobbleTolerance.DERIVE, derive=lambda p: int(p["base"]) * 2)
    with capture_a2kit_logs() as logs:
        out = _ctx({"base": 3}, "x", policy)
    assert out == 6
    events = [r for r in logs if r.get("event") == "llm_wobble"]
    assert len(events) == 1
    assert events[0]["field"] == "x"
    assert events[0]["tolerance"] == "derive"


def test_default_substitutes_and_logs() -> None:
    with capture_a2kit_logs() as logs:
        out = _ctx({}, "x", WobblePolicy(WobbleTolerance.DEFAULT, default="fallback"))
    assert out == "fallback"
    events = [r for r in logs if r.get("event") == "llm_wobble"]
    assert len(events) == 1
    assert events[0]["tolerance"] == "default"


def test_skip_raises_wobbleskip_and_logs() -> None:
    with capture_a2kit_logs() as logs, pytest.raises(WobbleSkip):
        _ctx({}, "x", WobblePolicy(WobbleTolerance.SKIP))
    events = [r for r in logs if r.get("event") == "llm_wobble"]
    assert len(events) == 1
    assert events[0]["tolerance"] == "skip"


def test_null_value_treated_as_missing() -> None:
    """Explicit null is the same wobble as omission — recover via the policy."""
    out = _ctx({"x": None}, "x", WobblePolicy(WobbleTolerance.DEFAULT, default="ok"))
    assert out == "ok"


def test_derive_without_callable_raises_keyerror() -> None:
    """DERIVE policy with no `derive` callable is a mis-declared policy."""
    with pytest.raises(KeyError):
        _ctx({}, "x", WobblePolicy(WobbleTolerance.DERIVE))


def test_raw_excerpt_bounded_in_log() -> None:
    huge = "z" * 5000
    with capture_a2kit_logs() as logs:
        apply_policy(
            {},
            "x",
            WobblePolicy(WobbleTolerance.DEFAULT, default=0),
            boundary="test",
            model="m",
            raw_excerpt=huge,
        )
    events = [r for r in logs if r.get("event") == "llm_wobble"]
    assert len(events) == 1
    assert len(events[0]["raw"]) <= 200
