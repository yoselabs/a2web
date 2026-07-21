"""Unit tests for `is_complete_small_page` — the pure complete-small-page predicate.

A strict sibling of `is_confirmed_empty`, keyed on observation logs directly (no
I/O). The promotion holds only under the full conjunction: no wall/subresource/
challenge evidence + an HTTP body + a browser regate that agreed the page is a bare
thin fallthrough (non-empty, under-floor, no empty marker). Unlike the empty
predicate there is NO URL-shape term.
"""

from __future__ import annotations

from a2web.actions.empty import is_complete_small_page
from a2web.decision_log import Observation, ObservationKind
from a2web.models import Verdict
from a2web.packages.block_detector import THIN_FALLTHROUGH

_URL = "https://example.com/"  # non-search — the predicate must NOT care


def _tier(verdict: Verdict, *, status_code: int = 0, subresource_blocks: int = 0) -> Observation:
    return Observation(
        kind=ObservationKind.tier_outcome,
        source="raw",
        verdict=verdict,
        authoritative=False,
        t_ms=1,
        status_code=status_code,
        subresource_blocks=subresource_blocks,
    )


def _gate(verdict: Verdict, *, source: str = "gate", subsystem: str | None = None) -> Observation:
    return Observation(
        kind=ObservationKind.gate_outcome, source=source, verdict=verdict, authoritative=False, t_ms=2, subsystem=subsystem
    )


def _regate_thin() -> Observation:
    """The browser's corroborating witness: a regate that is a bare thin fallthrough."""
    return _gate(Verdict.length_floor, source="regate", subsystem=THIN_FALLTHROUGH)


def _corroborated_log() -> list[Observation]:
    """HTTP body + initial thin gate + a browser regate agreeing it is thin."""
    return [
        _tier(Verdict.ok, status_code=200),
        _gate(Verdict.length_floor, subsystem=THIN_FALLTHROUGH),
        _regate_thin(),
    ]


def test_corroborated_thin_non_search_page_promotes() -> None:
    assert is_complete_small_page(_corroborated_log(), _URL) is True


def test_no_url_shape_term_search_and_non_search_both_promote() -> None:
    """The ONLY difference from is_confirmed_empty: no search-shaped-URL term."""
    assert is_complete_small_page(_corroborated_log(), "https://example.com/search?q=x") is True
    assert is_complete_small_page(_corroborated_log(), "https://example.com/about") is True


def test_no_browser_regate_does_not_promote() -> None:
    """HTTP thin read alone (no browser witness) is not enough."""
    log = [_tier(Verdict.ok, status_code=200), _gate(Verdict.length_floor, subsystem=THIN_FALLTHROUGH)]
    assert is_complete_small_page(log, _URL) is False


def test_subresource_block_evidence_forbids_promotion() -> None:
    log = [*_corroborated_log(), _tier(Verdict.ok, status_code=200, subresource_blocks=1)]
    assert is_complete_small_page(log, _URL) is False


def test_hard_wall_evidence_forbids_promotion() -> None:
    log = [*_corroborated_log(), _gate(Verdict.blank_page)]
    assert is_complete_small_page(log, _URL) is False


def test_challenge_status_forbids_promotion() -> None:
    log = [_tier(Verdict.connection_error, status_code=403), *_corroborated_log()]
    assert is_complete_small_page(log, _URL) is False


def test_empty_marker_regate_is_not_a_small_page() -> None:
    """A browser regate carrying the empty-result marker is the empty predicate's
    territory (is_confirmed_empty), not this one — the corroboration term is
    specifically the THIN_FALLTHROUGH marker, not empty_result."""
    log = [
        _tier(Verdict.ok, status_code=200),
        _gate(Verdict.length_floor, subsystem="empty_result"),
        _gate(Verdict.length_floor, source="regate", subsystem="empty_result"),
    ]
    assert is_complete_small_page(log, _URL) is False


def test_no_http_body_does_not_promote() -> None:
    """Only a browser regate, no winning HTTP tier → not corroborated by two paths."""
    log = [_tier(Verdict.connection_error, status_code=0), _regate_thin()]
    assert is_complete_small_page(log, _URL) is False


def test_js_required_shell_fingerprint_forbids_promotion() -> None:
    """An under-rendered SPA — a `js_required` gate fingerprint plus a thin browser
    regate — is a wall-shaped miss, NOT a complete small page. The fingerprint
    disqualifies it even though the browser regate looks like a bare thin page."""
    log = [
        _tier(Verdict.ok, status_code=200),
        _gate(Verdict.length_floor, subsystem="js_required"),
        _regate_thin(),
    ]
    assert is_complete_small_page(log, _URL) is False


def test_thin_browser_response_fingerprint_forbids_promotion() -> None:
    """A known JS-heavy host's thin browser response is a shell fingerprint too."""
    log = [
        _tier(Verdict.ok, status_code=200),
        _gate(Verdict.length_floor, subsystem="thin_browser_response"),
        _regate_thin(),
    ]
    assert is_complete_small_page(log, _URL) is False
