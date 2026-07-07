"""content-aware refinement: dimensional refinement axes on a partial listing.

Covers the boundary parse, the seam projection, and the `build_ask_response`
gate (axes ride the wire ONLY on a partial listing; omitted on complete /
non-listing pages) plus the omit-empty wire discipline.
"""

from __future__ import annotations

import json

from a2web.fetcher_response import _project_routing, build_ask_response
from a2web.models import (
    Confidence,
    FetchResponse,
    FetchStatus,
    RefinementAxis,
    RouterPayload,
)
from a2web.packages.llm_extract.extractor import _RoutingResult, _split_answer_and_routing
from a2web.packages.llm_extract.router_payload import RouterPayload as RouterBoundary
from a2web.packages.llm_extract.wobble import unwrap


def _routing(text: str) -> RouterBoundary | None:
    _answer, wobbled = _split_answer_and_routing(text)
    if wobbled is None:
        return None
    result: _RoutingResult = unwrap(wobbled)
    return result.payload


def _listing_envelope(*, axes: list[dict], total_seen: int | None = 1123) -> str:
    payload: dict[str, object] = {
        "answer": "The cheapest crimping tools shown range 270-495 TL.",
        "structural_form": "listing",
        "shape": "records",
        "refinement_axes": axes,
    }
    if total_seen is not None:
        payload["item_total_seen"] = total_seen
    return json.dumps(payload)


# --------------------------------------------------------------------- #
# Boundary parse (extractor)
# --------------------------------------------------------------------- #


def test_boundary_parses_axes_and_total_seen() -> None:
    boundary = _routing(
        _listing_envelope(
            axes=[
                {"dimension": "price floor", "how": "add a minimum price"},
                {"dimension": "sort order", "how": "sort by rating"},
            ]
        )
    )
    assert boundary is not None
    assert boundary.item_total_seen == 1123
    assert [a.dimension for a in boundary.refinement_axes] == ["price floor", "sort order"]
    assert boundary.refinement_axes[0].how == "add a minimum price"


def test_boundary_skips_malformed_axis_entries() -> None:
    boundary = _routing(
        _listing_envelope(
            axes=[
                {"dimension": "brand", "how": "narrow to one brand"},
                {"how": "no dimension key"},  # dropped — no dimension
                "not-a-dict",  # dropped
                {"dimension": "", "how": "empty dimension"},  # dropped
            ]
        )
    )
    assert boundary is not None
    assert [a.dimension for a in boundary.refinement_axes] == ["brand"]


def test_boundary_absent_axes_default_empty() -> None:
    boundary = _routing(json.dumps({"answer": "x", "structural_form": "article", "shape": "prose"}))
    assert boundary is not None
    assert boundary.refinement_axes == ()
    assert boundary.item_total_seen is None


def test_boundary_rejects_bool_total_seen() -> None:
    # JSON `true` is an int subtype in Python — must not be read as a count.
    boundary = _routing(json.dumps({"answer": "x", "structural_form": "listing", "shape": "records", "item_total_seen": True}))
    assert boundary is not None
    assert boundary.item_total_seen is None


# --------------------------------------------------------------------- #
# Seam projection
# --------------------------------------------------------------------- #


def test_projection_maps_axes_to_mirror() -> None:
    boundary = _routing(_listing_envelope(axes=[{"dimension": "brand", "how": "narrow to one brand"}]))
    mirror = _project_routing(boundary)
    assert mirror is not None
    assert mirror.refinement_axes == [RefinementAxis(dimension="brand", how="narrow to one brand")]
    assert mirror.item_total_seen == 1123


# --------------------------------------------------------------------- #
# build_ask_response gate + wire discipline
# --------------------------------------------------------------------- #


def _fr(*, structural_form: str, axes: list[RefinementAxis], items_loaded: int | None, items_total: int | None) -> FetchResponse:
    routing = RouterPayload(
        answer="answer",
        structural_form=structural_form,  # type: ignore[arg-type]
        shape="records" if structural_form == "listing" else "prose",  # type: ignore[arg-type]
        refinement_axes=axes,
    )
    return FetchResponse(
        url="https://shop.example/ara?q=x&siralama=artanFiyat",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.high,
        extracted_answer="answer",
        routing=routing,
        items_loaded=items_loaded,
        items_total=items_total,
    )


def test_axes_present_on_partial_listing() -> None:
    axes = [RefinementAxis(dimension="price floor", how="add a minimum price")]
    ask = build_ask_response(
        _fr(structural_form="listing", axes=axes, items_loaded=36, items_total=1123),
        include_content=False,
        debug=False,
    )
    assert ask.refinement_axes == axes
    wire = ask.model_dump()
    assert wire["refinement_axes"] == [{"dimension": "price floor", "how": "add a minimum price"}]


def test_axes_dropped_on_complete_listing() -> None:
    # Complete listing: items_loaded is None (build_response nulls the counts).
    axes = [RefinementAxis(dimension="price floor", how="add a minimum price")]
    ask = build_ask_response(
        _fr(structural_form="listing", axes=axes, items_loaded=None, items_total=None),
        include_content=False,
        debug=False,
    )
    assert ask.refinement_axes == []
    assert "refinement_axes" not in ask.model_dump()


def test_axes_dropped_on_non_listing() -> None:
    axes = [RefinementAxis(dimension="price floor", how="add a minimum price")]
    ask = build_ask_response(
        _fr(structural_form="article", axes=axes, items_loaded=None, items_total=None),
        include_content=False,
        debug=False,
    )
    assert ask.refinement_axes == []
    assert "refinement_axes" not in ask.model_dump()


def test_empty_axes_omitted_from_wire() -> None:
    ask = build_ask_response(
        _fr(structural_form="listing", axes=[], items_loaded=36, items_total=1123),
        include_content=False,
        debug=False,
    )
    assert "refinement_axes" not in ask.model_dump()
