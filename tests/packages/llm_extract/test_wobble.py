"""a2web's binding of the shelf `llm-wobble` funnel.

The funnel MACHINERY (fence strip, decode, per-field policy, recovery, the
`Wobbled` token) is tested in the shelf package `llm_wobble`. What a2web must
verify here is the BINDING: that `wobble/__init__.py` injects a2web's managed
`a2web` logger, so every `llm_wobble` recovery drains through a2web's sinks and
not the package's default channel. `capture_logs` attaches to the `a2web`
logger — if the shim stopped injecting, the event would land on the `llm_wobble`
logger instead and these captures would come back empty.
"""

from __future__ import annotations

from a2web.packages.llm_extract.wobble import (
    WobblePolicy,
    WobbleTolerance,
    parse_list_with_policy,
    parse_with_policy,
    unwrap,
)
from tests._helpers.log_capture import capture_logs


def test_shim_parses_through_funnel() -> None:
    wobbled = parse_with_policy(
        '{"x": 1}',
        policies={"x": WobblePolicy(WobbleTolerance.STRICT)},
        into=lambda d: d["x"],
        boundary="test",
        model="m",
    )
    assert unwrap(wobbled) == 1


def test_shim_injects_a2web_logger_on_recovery() -> None:
    with capture_logs() as logs:
        parse_with_policy(
            '{"a": 1}',
            policies={
                "a": WobblePolicy(WobbleTolerance.STRICT),
                "b": WobblePolicy(WobbleTolerance.DEFAULT, default=0),
            },
            into=dict,
            boundary="test",
            model="m",
        )
    events = [r for r in logs if r.get("event") == "llm_wobble"]
    assert len(events) == 1, "the DEFAULT recovery for `b` must emit on a2web's managed logger"
    assert events[0]["field"] == "b"
    assert events[0]["tolerance"] == "default"


def test_shim_injects_a2web_logger_on_list_drop() -> None:
    with capture_logs() as logs:
        wobbled = parse_list_with_policy(
            '[{"k": 1}, "bad", {"k": 2}]',
            item=lambda d: d.get("k"),
            boundary="test",
            model="m",
        )
    assert unwrap(wobbled) == [1, 2]
    assert [r for r in logs if r.get("event") == "llm_wobble"], "dropped entry must emit on a2web's logger"
