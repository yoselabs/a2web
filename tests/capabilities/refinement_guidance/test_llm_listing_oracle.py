"""content-aware refinement: LLM-side partialness detection (language-gap close).

`_apply_llm_listing_oracle` is a strict superset of the regex oracle: it fires
ONLY when the regex found no numeric total, only on a confirmed listing, and it
never overrides a regex verdict.
"""

from __future__ import annotations

from a2web.fetcher import FetchContext, _apply_llm_listing_oracle
from a2web.packages.llm_extract.router_payload import RouterPayload as RouterBoundary


def _fc(*, record_count: int | None, regex_oracle_total: int | None, item_total_seen: int | None) -> FetchContext:
    fc = FetchContext(
        started_at=None,  # type: ignore[arg-type]
        start_perf=0.0,
        profile_hash="h",
        sqlite=None,  # type: ignore[arg-type]  # unused by the helper under test
        bypass_cache=False,
        url="https://shop.example/ara?q=x",
        final_url="https://shop.example/ara?q=x",
    )
    fc.record_count = record_count
    fc.regex_oracle_total = regex_oracle_total
    if item_total_seen is not None:
        fc.routing = RouterBoundary(
            answer="a",
            structural_form="listing",
            shape="records",
            item_total_seen=item_total_seen,
        )
    return fc


def test_fires_when_regex_found_no_oracle() -> None:
    # The language-gap case: regex noun list missed the total, model read 1123.
    fc = _fc(record_count=36, regex_oracle_total=None, item_total_seen=1123)
    _apply_llm_listing_oracle(fc)
    assert fc.items_loaded == 36
    assert fc.items_total == 1123
    assert fc.items_more is False


def test_does_not_override_regex_oracle() -> None:
    # Regex already extracted a numeric oracle (deemed complete) — the LLM path
    # must NOT override it, even if the model reports a larger count.
    fc = _fc(record_count=40, regex_oracle_total=40, item_total_seen=9999)
    _apply_llm_listing_oracle(fc)
    assert fc.items_total is None  # untouched — regex authoritative


def test_silent_on_non_listing() -> None:
    fc = _fc(record_count=None, regex_oracle_total=None, item_total_seen=1123)
    _apply_llm_listing_oracle(fc)
    assert fc.items_loaded is None
    assert fc.items_total is None


def test_silent_when_within_tolerance() -> None:
    # Model total meets the parsed count — not partial, no signal.
    fc = _fc(record_count=40, regex_oracle_total=None, item_total_seen=40)
    _apply_llm_listing_oracle(fc)
    assert fc.items_total is None


def test_silent_when_no_routing() -> None:
    fc = _fc(record_count=36, regex_oracle_total=None, item_total_seen=None)
    _apply_llm_listing_oracle(fc)
    assert fc.items_total is None
