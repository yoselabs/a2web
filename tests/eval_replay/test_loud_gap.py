"""An un-frozen egress is a red, fixable test — never a live call.

Replay refuses to fall through to the network/browser/LLM when a case
exercises an egress the cassette does not cover; it raises `CassetteMiss`
naming the case, the tier, and the `make eval-refresh` fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eval._capture.corpus import CaseBaseline, CaseInputs, ReplayCase
from tests.eval_replay.harness import CassetteBrowserPool, CassetteMiss, make_replay_fetch_bytes


def _case(**kw: Any) -> ReplayCase:
    base: dict[str, Any] = {
        "slug": "gap",
        "url": "https://example.com/x",
        "question": None,
        "failure_class": "A",
        "tags": frozenset(),
        "corpus": "regression",
        "path": Path("."),
        "inputs": CaseInputs(),
        "baseline": CaseBaseline(),
    }
    base.update(kw)
    return ReplayCase(**base)


async def test_raw_miss_raises_and_names_the_fix() -> None:
    case = _case(inputs=CaseInputs(http={}))
    replay_fetch = make_replay_fetch_bytes(case)
    with pytest.raises(CassetteMiss) as excinfo:
        await replay_fetch("https://example.com/never-frozen")
    msg = str(excinfo.value)
    assert "tier=raw" in msg
    assert "make eval-refresh CASE=regression/gap" in msg
    assert excinfo.value.tier == "raw"


async def test_browser_miss_when_no_rendered_dom() -> None:
    case = _case(inputs=CaseInputs(rendered_html=None))
    backend = CassetteBrowserPool(case)
    with pytest.raises(CassetteMiss) as excinfo:
        await backend.render("https://example.com/x", cookies=[], budget_s=30.0, js_heavy=False)
    assert excinfo.value.tier == "browser"
    assert "make eval-refresh CASE=regression/gap" in str(excinfo.value)


async def test_browser_hit_serves_frozen_dom() -> None:
    case = _case(inputs=CaseInputs(rendered_html="<html>frozen</html>"))
    backend = CassetteBrowserPool(case)
    page = await backend.render("https://example.com/x", cookies=[], budget_s=30.0, js_heavy=False)
    assert page.html == "<html>frozen</html>"
    assert page.final_url == "https://example.com/x"
    assert page.outcome.value == "ok"


# --------------------------------------------------------------------- #
# Cassette format — a legacy record must FAIL, never silently degrade
# --------------------------------------------------------------------- #


async def test_legacy_cassette_without_routing_fails_loud() -> None:
    """A pre-routing cassette must raise, not quietly replay the degraded branch.

    This is the regression that motivated the whole change: the harness simply
    omitted `routing=`, so it defaulted to `None` and EVERY replayed case ran
    the routing-lost branch while reporting success — for 16 cases, invisibly.
    A tolerant fallback here would restore that exact behaviour under the name
    of backward compatibility, so the absence of the key is an ERROR.
    """
    from tests.eval_replay.harness import CassetteLlm

    legacy = {"answer": "a", "model": "m", "template_name": "extract_router_v1"}
    case = _case(inputs=CaseInputs(llm={"extract": legacy}))
    with pytest.raises(CassetteMiss) as excinfo:
        await CassetteLlm(case).extract(content="c", ask="q", request_routing=True)
    msg = str(excinfo.value)
    assert "predates the routing field" in msg
    assert "eval-refresh" in msg, "the error must name the one-command fix"


async def test_cassette_can_record_a_genuinely_lost_payload() -> None:
    """`routing: null` is expressible and distinct from a missing key.

    Without this the loud failure above would be un-silenceable for a case that
    legitimately exercises a lost payload, and the only escape would be to
    weaken the check.
    """
    from tests.eval_replay.harness import CassetteLlm

    recorded_lost = {"answer": "a", "model": "m", "template_name": "extract_router_v1", "routing": None}
    case = _case(inputs=CaseInputs(llm={"extract": recorded_lost}))
    result = await CassetteLlm(case).extract(content="c", ask="q", request_routing=True)
    assert result.routing is None
    assert result.answer == "a", "the answer still replays; only routing was recorded as lost"
