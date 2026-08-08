"""query-title-mismatch (a2web-byy, the harder half of a2web-axb).

Source: `docs/findings/2026-08-07-a2web-call-trace-audit.md` §4a2 — a
hepsiburada `"pindstrup"` search returned "Gölgelik File" (shade cloth); a
kaspi `"AMT M-1"` search returned unrelated computer/auto parts. Unlike
`served_url_differs` (§4a, same-domain-vs-cross-domain — a deterministic
URL-level signal), this shape has the fetch landing on the RIGHT site, but
the site's own search (or the DOM record miner) returning a different
product/category than the caller's query names. No URL-level signal exists
for this; it needs the query compared against what the listing actually
served.

Compared against served ITEM titles (`record_set.records[].heading_text`),
not the page's own `<title>` — a search-results page's title conventionally
echoes the query term regardless of result relevance, which would show zero
mismatch in exactly the cases this exists to catch.

Deliberately scoped to LISTING pages, zero-overlap only. The harder
confusable-model-variant shape on a single product page (Lenovo 15AKP10 asked,
15IRX10 served) is explicitly out of scope (`flag-query-title-mismatch`
design.md Non-Goals) — no listing item titles exist to compare against there.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from record_mine import Record, RecordSet

from a2web.decision_log import ObservationKind
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.fetcher.verdict.terminal import _apply_terminal
from a2web.fetcher_response import _normalize_tokens, _query_shares_no_term_with, build_response
from a2web.models import Confidence, Verdict
from a2web.packages.llm_extract import RouterPayload

_LONG_BODY = "x" * 2500  # clears _confidence_for's high threshold on its own


def _records(*titles: str) -> RecordSet:
    return RecordSet(
        records=tuple(
            Record(text=t, links=(), heading_text=t, heading_link=(t, f"https://x/{i}"), depth=0, markdown=f"- {t}")
            for i, t in enumerate(titles)
        ),
        container="ul",
        child_signature="li",
        max_depth=0,
    )


def _fc(*, ask: str | None, structural_form: str | None, titles: tuple[str, ...], content_md: str = _LONG_BODY) -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
            requested_url="https://shop.example/search?q=x",
            ask=ask,
        ),
        resources=FetchResources(sqlite=None),
        url="https://shop.example/search?q=x",
        final_url="https://shop.example/search?q=x",
        content_md=content_md,
    )
    if structural_form is not None:
        fc.routing = RouterPayload(answer="some answer", structural_form=structural_form, shape="records")
    if titles:
        fc.record_set = _records(*titles)
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    _apply_terminal(fc)
    return fc


# --------------------------------------------------------------------- #
# _normalize_tokens / _query_shares_no_term_with — pure helper
# --------------------------------------------------------------------- #


def test_normalize_tokens_casefolds_and_splits() -> None:
    assert _normalize_tokens("RTX 4090 Price, Stock!") == {"rtx", "4090", "price", "stock"}


def test_normalize_tokens_drops_short_tokens() -> None:
    assert "a" not in _normalize_tokens("a RTX")
    assert "rtx" in _normalize_tokens("a RTX")


def test_normalize_tokens_handles_turkish_diacritics() -> None:
    # NFKD decomposes Turkish diacritics; the same brand token normalizes the
    # same way on both the query and the served (Turkish) side without a stemmer.
    assert "pindstrup" in _normalize_tokens("Pindstrup Törf İthal 25L")


def test_stopword_stripping_leaves_nothing_means_no_signal() -> None:
    assert _query_shares_no_term_with("price, stock", ["Anything Whatsoever"]) is False


def test_stopword_stripping_keeps_the_substantive_term() -> None:
    # "RTX 4090" survives stopword stripping; matches a served title -> no mismatch.
    assert _query_shares_no_term_with("RTX 4090 price, stock", ["Sapphire RTX 4090 Nitro+"]) is False


def test_any_one_item_overlapping_is_not_a_mismatch() -> None:
    assert _query_shares_no_term_with("pindstrup", ["Gölgelik File", "Pindstrup Blonde Torf 25L", "Kalsiyum Nitrat"]) is False


def test_zero_overlap_across_every_item_is_a_mismatch() -> None:
    assert _query_shares_no_term_with("pindstrup", ["Gölgelik File", "Kalsiyum Nitrat", "Plagron"]) is True


def test_no_served_titles_is_not_a_mismatch() -> None:
    """Vacuous case: nothing to compare against is not evidence of a mismatch."""
    assert _query_shares_no_term_with("pindstrup", []) is False


# --------------------------------------------------------------------- #
# build_response — wired end to end
# --------------------------------------------------------------------- #


@pytest.mark.protects(
    "spec:fetch-response",
    "Requirement: A listing whose served items share no term with the query caps confidence and is flagged",
)
def test_zero_overlap_listing_caps_high_confidence() -> None:
    fc = _fc(ask="pindstrup", structural_form="listing", titles=("Gölgelik File", "Kalsiyum Nitrat"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium
    assert any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_any_overlapping_item_is_not_flagged() -> None:
    fc = _fc(ask="RTX 4090", structural_form="listing", titles=("Sapphire RTX 4090 Nitro+", "Unrelated Widget"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.high
    assert not any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_non_listing_fetch_is_not_checked() -> None:
    fc = _fc(ask="pindstrup", structural_form="product", titles=("Gölgelik File", "Kalsiyum Nitrat"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.high
    assert not any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_no_routing_classification_is_not_checked() -> None:
    fc = _fc(ask="pindstrup", structural_form=None, titles=("Gölgelik File", "Kalsiyum Nitrat"))
    fr = build_response(fc)
    assert not any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_no_ask_is_not_checked() -> None:
    """fetch_raw shape: no query at all -> nothing to compare, never flagged."""
    fc = _fc(ask=None, structural_form="listing", titles=("Gölgelik File", "Kalsiyum Nitrat"))
    fr = build_response(fc)
    assert not any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_empty_after_stopword_strip_is_not_checked() -> None:
    fc = _fc(ask="price, stock", structural_form="listing", titles=("Gölgelik File", "Kalsiyum Nitrat"))
    fr = build_response(fc)
    assert fr.confidence == Confidence.high
    assert not any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_cap_never_raises_confidence() -> None:
    fc = _fc(ask="pindstrup", structural_form="listing", titles=("Gölgelik File",), content_md="short body under the high-confidence floor")
    fr = build_response(fc)
    assert fr.confidence == Confidence.medium  # already medium/low from content length, not raised
    assert any(h.code == "query_title_mismatch" for h in fr.operator_hints)


def test_cap_does_not_double_apply_below_medium_with_served_url_differs() -> None:
    """Both checks can fire together; confidence lands at medium either way,
    never lower purely from stacking two downgrade-only caps."""
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
            requested_url="https://shop.example/search?q=pindstrup",
            ask="pindstrup",
        ),
        resources=FetchResources(sqlite=None),
        url="https://shop.example/search?q=pindstrup",
        final_url="https://other-site.example/search?q=pindstrup",  # cross-domain too
        content_md=_LONG_BODY,
    )
    fc.routing = RouterPayload(answer="a", structural_form="listing", shape="records")
    fc.record_set = _records("Gölgelik File", "Kalsiyum Nitrat")
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    _apply_terminal(fc)

    fr = build_response(fc)
    assert fr.confidence == Confidence.medium
    codes = {h.code for h in fr.operator_hints}
    assert "served_url_differs" in codes
    assert "query_title_mismatch" in codes
