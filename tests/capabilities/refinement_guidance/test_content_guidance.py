"""content-aware refinement: per-kind content guidance + query-param context bundle."""

from __future__ import annotations

from a2web.content_guidance import kind_guidance
from a2web.domain import parse_query_params
from a2web.fetcher_response import build_ask_response
from a2web.models import Confidence, FetchResponse, FetchStatus, RouterPayload

# --------------------------------------------------------------------- #
# kind_guidance — per-kind, total, site-free
# --------------------------------------------------------------------- #


def test_kind_guidance_listing_mentions_completeness_and_bias() -> None:
    text = kind_guidance("listing")
    assert text is not None
    lowered = text.lower()
    assert "complete" in lowered
    assert "bias" in lowered


def test_kind_guidance_unknown_and_none_are_silent() -> None:
    assert kind_guidance("code") is None
    assert kind_guidance(None) is None


# --------------------------------------------------------------------- #
# content_guidance surfaces as an info hint on the ask envelope
# --------------------------------------------------------------------- #


def _fr(structural_form: str) -> FetchResponse:
    return FetchResponse(
        url="https://shop.example/x",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.high,
        extracted_answer="answer",
        routing=RouterPayload(
            answer="answer",
            structural_form=structural_form,  # type: ignore[arg-type]
            shape="records" if structural_form == "listing" else "prose",  # type: ignore[arg-type]
        ),
    )


def test_content_guidance_hint_emitted_for_known_kind() -> None:
    ask = build_ask_response(_fr("listing"), include_content=False, debug=False)
    codes = [h.code for h in ask.operator_hints]
    assert "content_guidance" in codes


def test_no_content_guidance_hint_for_kind_without_entry() -> None:
    ask = build_ask_response(_fr("code"), include_content=False, debug=False)
    codes = [h.code for h in ask.operator_hints]
    assert "content_guidance" not in codes


# --------------------------------------------------------------------- #
# parse_query_params — verbatim, uninterpreted, total
# --------------------------------------------------------------------- #


def test_params_parsed_verbatim() -> None:
    params = parse_query_params("https://shop.example/ara?q=ez+rj45&siralama=artanFiyat")
    assert params == [("q", "ez rj45"), ("siralama", "artanFiyat")]


def test_params_preserve_order_and_repeats() -> None:
    params = parse_query_params("https://x/y?a=1&b=2&a=3")
    assert params == [("a", "1"), ("b", "2"), ("a", "3")]


def test_params_blank_value_surfaced() -> None:
    assert parse_query_params("https://x/y?filter=") == [("filter", "")]


def test_params_empty_and_malformed_are_total() -> None:
    assert parse_query_params("https://x/y") == []
    assert parse_query_params("") == []
    assert parse_query_params("not a url") == []
