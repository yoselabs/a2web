"""requested-identity-vs-served-content (a2web-axb).

Source: `docs/findings/2026-08-07-a2web-call-trace-audit.md` §4a — a
hepsiburada product URL served sikayetvar.com "Decathlon Sikayet" content
about bike assembly; a trendyol request served a hepsiburada title. Both shipped
`confidence: high` with nothing telling the caller the served page was not the
requested one.

Minimum viable check (the bd issue's own words): compare the served page's
registrable domain against the requested URL's; on a cross-domain landing, cap
confidence and emit an explicit `served_url_differs` marker rather than assert
`high` about a page that may not be the one requested.

Deliberately NOT flagging same-site redirects (canonicalization, a
captcha-host rewrite back to origin) — those are the common, correct case, and
over-flagging them would make the hint noise instead of signal.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.verdict.terminal import _apply_terminal
from a2web.fetcher_response import build_response
from a2web.models import Confidence, Verdict


def _fc(*, requested_url: str, final_url: str, content_md: str) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
            requested_url=requested_url,
        ),
        resources=FetchResources(sqlite=None),
        url=requested_url,
        final_url=final_url,
        content_md=content_md,
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    _apply_terminal(fc)
    return fc


_LONG_BODY = "x" * 2500  # clears _confidence_for's high threshold on its own


@pytest.mark.protects("spec:fetch-response", "Requirement: a cross-domain landing caps confidence and is flagged")
def test_cross_domain_landing_caps_high_confidence_to_medium() -> None:
    fc = _fc(
        requested_url="https://www.hepsiburada.com/urun/some-drill-p123",
        final_url="https://www.sikayetvar.com/decathlon/bike-assembly",
        content_md=_LONG_BODY,
    )
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium, "a cross-domain landing shipped high confidence unchallenged"
    assert any(h.code == "served_url_differs" for h in fr.operator_hints)


def test_same_registrable_domain_redirect_is_not_flagged() -> None:
    """A subdomain/path redirect within the same site is the common, correct case."""
    fc = _fc(
        requested_url="https://hepsiburada.com/urun/some-drill-p123",
        final_url="https://www.hepsiburada.com/urun/some-drill-p123-canonical",
        content_md=_LONG_BODY,
    )
    fr = build_response(fc)
    assert fr.confidence == Confidence.high
    assert not any(h.code == "served_url_differs" for h in fr.operator_hints)


def test_cross_domain_landing_never_raises_a_low_confidence_to_medium() -> None:
    """The cap is downgrade-only: a short body's already-medium confidence is untouched."""
    fc = _fc(
        requested_url="https://www.hepsiburada.com/urun/p123",
        final_url="https://www.sikayetvar.com/decathlon/bike-assembly",
        content_md="short body under the high-confidence length floor",
    )
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium
    assert any(h.code == "served_url_differs" for h in fr.operator_hints)
