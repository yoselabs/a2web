"""A declared JSON-LD type a2web does not recognise must still render (ADR-0018).

`_ld_json_to_markdown` gated on `_ENTITY_TYPES`, an eight-name allowlist —
`Product`, `Article`, `NewsArticle`, `LocalBusiness`, `Organization`,
`ContactPoint`, `Event`, `Recipe`. Every other declared type rendered as
**nothing**, silently, with no signal that a page's own structured description
of itself had been discarded.

Measured cost, `eval/spikes/declaration_rate_v6.py` (2026-08-03): over a2web's
44-URL corpus, 7 retrieved pages declare something subject-level and a closed
list drops **4 of them** — a 74-field `ProductGroup`, a 51-field
`DiscussionForumPosting`, a 35-field `NewsMediaOrganization`, and a `Store`.
The richest declaration on the corpus was the one being thrown away.

The renderer never needed the list: `_single_entity_md` takes the type as a
plain string LABEL and reads the entity's own keys. So this is the ADR-0018
shape — *a vocabulary a2web holds is a label table, never a gate*.

These tests are written against types deliberately ABSENT from the old
allowlist, so they fail if the gate is ever reintroduced under any name.
"""

from __future__ import annotations

import pytest

from a2web.packages.structured_render import _ld_json_to_markdown

#: Every one of these was rendered as "" by the eight-name allowlist. Three are
#: observed on a2web's own corpus; `JobPosting` / `Course` / `Dataset` are the
#: cases ADR-0018 was argued from.
_FORMERLY_DROPPED = [
    "ProductGroup",
    "DiscussionForumPosting",
    "NewsMediaOrganization",
    "Store",
    "JobPosting",
    "Course",
    "Dataset",
    "Movie",
    "Book",
    "SoftwareApplication",
]


@pytest.mark.parametrize("declared_type", _FORMERLY_DROPPED)
def test_unrecognised_type_still_renders_its_fields(declared_type: str) -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": declared_type,
        "name": "The Thing",
        "identifier": "SKU-991",
        "description": "A description the page published about itself.",
    }
    md = _ld_json_to_markdown(payload)

    assert md, f"a declared `{declared_type}` rendered as nothing — the type gate is back"
    # The type survives as a LABEL, verbatim, not normalised into a known name.
    assert declared_type in md
    # And the entity's own fields come through, which is the actual payload.
    assert "The Thing" in md
    assert "SKU-991" in md
    assert "A description the page published" in md


def test_a_recognised_type_is_unchanged() -> None:
    """The other direction — removing the gate must not alter the old path.

    Without this, deleting the gate could have regressed the eight types that
    always worked and the parametrised test above would still pass.
    """
    md = _ld_json_to_markdown(
        {"@context": "https://schema.org", "@type": "Product", "name": "Widget", "sku": "W-1"},
    )
    assert "Product" in md
    assert "Widget" in md
    assert "W-1" in md


def test_a_typeless_entity_still_renders() -> None:
    """No `@type` at all is not a reason to discard the fields."""
    md = _ld_json_to_markdown({"name": "Untyped", "price": "42"})
    assert "Untyped" in md
    assert "42" in md


def test_chrome_with_no_renderable_field_stays_silent() -> None:
    """Removing the gate must not turn chrome into noise.

    An entity whose only keys are JSON-LD machinery or media references has
    nothing to render and must produce "", or every page would gain a wall of
    `WebSite` / `ImageObject` stubs. This is what makes the gate unnecessary
    rather than merely wrong: emptiness is decided by CONTENT, not by type.
    """
    md = _ld_json_to_markdown({"@type": "ImageObject", "@id": "#logo", "image": "https://x/y.png"})
    assert md.strip() == ""


def test_entity_flood_is_capped_and_the_cut_is_declared() -> None:
    """A page publishing many entities is bounded — and says so.

    A bound is legitimate where a vocabulary is not: it cuts by volume, which
    a2web can measure, rather than by meaning, which it cannot. But an
    undeclared cut is the ADR-0009 harm — the reader cannot tell "the page
    published this much" from "a2web stopped rendering".
    """
    entries = [{"@type": "Offer", "name": f"Offer {i}", "price": str(i)} for i in range(30)]
    md = _ld_json_to_markdown(entries)

    assert "Offer 0" in md
    assert "not shown" in md, "the truncation must be declared, not silent"
    # The note reports a real remainder, not a constant.
    assert "30" not in md.split("_…")[-1], "the note should count what was DROPPED, not the total"
