"""a2web-7bj.7: a failed browser rung caps confidence to medium.

A DHL tracking call returned `confidence: high` on the answer "This page does
not provide the current status ... for tracking number 7957139164" — in the
same envelope as `browser_internal_error` AND `browser_unavailable` hints. If
a browser rung was dispatched and never completed, confidence in whatever
content DID land cannot be `high`: the page may well have had the real answer
behind the render that failed. A confident absence claim next to a failed
retrieval rung is the ADR-0009 harm wearing a different hat.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.verdict.terminal import _apply_terminal
from a2web.fetcher_response import build_response
from a2web.hints import browser_internal_error_hint, browser_unavailable_hint
from a2web.models import Confidence, Verdict

_LONG_BODY = "x" * 2500  # clears _confidence_for's high threshold on its own


def _fc(*, content_md: str, browser_hint=None) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
            requested_url="https://www.dhl.com/track?id=7957139164",
        ),
        resources=FetchResources(sqlite=None),
        url="https://www.dhl.com/track?id=7957139164",
        final_url="https://www.dhl.com/track?id=7957139164",
        content_md=content_md,
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    if browser_hint is not None:
        fc.operator_hints.append(browser_hint)
    _apply_terminal(fc)
    return fc


@pytest.mark.protects("spec:fetch-response", "Requirement: A failed browser rung caps confidence")
def test_browser_internal_error_caps_high_confidence_to_medium() -> None:
    fc = _fc(content_md=_LONG_BODY, browser_hint=browser_internal_error_hint("net::ERR_CONNECTION_RESET", rung="browser"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium, "a failed browser rung shipped high confidence unchallenged"


@pytest.mark.protects("spec:fetch-response", "Requirement: A failed browser rung caps confidence")
def test_browser_unavailable_caps_high_confidence_to_medium() -> None:
    fc = _fc(content_md=_LONG_BODY, browser_hint=browser_unavailable_hint("no binary", rung="browser_robust"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium


def test_no_browser_failure_leaves_high_confidence_untouched() -> None:
    fc = _fc(content_md=_LONG_BODY, browser_hint=None)
    fr = build_response(fc)
    assert fr.confidence == Confidence.high


def test_failed_browser_rung_never_raises_an_already_low_confidence() -> None:
    """The cap is downgrade-only: a short body's already-medium confidence is untouched."""
    fc = _fc(
        content_md="short body under the high-confidence length floor",
        browser_hint=browser_internal_error_hint("boom", rung="browser"),
    )
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium
