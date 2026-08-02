"""The `llm_wobble` event the routing mirror emits on a closed-enum violation.

`_project_routing` is the fourth site on the unified `llm_wobble` key, and the
only one that reaches it by pydantic validation rather than JSON parsing. Until
2026-08-02 NOTHING asserted the event at all: not that it fires, not what it
names, not that a surviving `answer` still reaches the caller. The `field=` value
— the one thing an operator greps this key for — was produced by hand-rolled
duck-typing over `exc.errors()` that reported only the first error and fell back
to `"unknown"` whenever the first `loc` was empty.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from a2web.fetcher_response import _project_routing
from a2web.packages.llm_extract import RouterPayload as RouterBoundary

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def wobbles() -> Iterator[list[dict[str, object]]]:
    """Every `llm_wobble` payload emitted, captured off the `a2web` logger itself.

    Not `caplog`: the `a2web` logger sets `propagate=False` (MCP is stdio, an
    escaped record corrupts the JSON-RPC stream), so caplog's root handler sees
    these records only when some *other* test has left propagation on. An earlier
    version of this file did use `caplog` — it passed in isolation and failed in
    the full suite, which is the giveaway: it was capturing by accident, and on
    the other side of that coin is a version that passes by accident and asserts
    nothing.
    """
    captured: list[dict[str, object]] = []

    class _Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage() == "llm_wobble":
                captured.append(dict(getattr(record, "fields", {})))

    logger = logging.getLogger("a2web")
    sink = _Sink(level=logging.WARNING)
    previous = logger.level
    logger.addHandler(sink)
    logger.setLevel(logging.WARNING)
    try:
        yield captured
    finally:
        logger.removeHandler(sink)
        logger.setLevel(previous)


def _boundary(**overrides: object) -> RouterBoundary:
    """A valid router boundary, so an override is the ONLY violation present."""
    fields: dict[str, object] = {
        "answer": "the page says forty-two.",
        "structural_form": "article",
        "shape": "prose",
    }
    fields.update(overrides)
    return RouterBoundary(**fields)  # ty: ignore[missing-argument]


def test_a_valid_boundary_projects_and_emits_nothing(wobbles: list[dict[str, object]]) -> None:
    """The anti-vacuity floor: the violation cases below must be the violation.

    Without this, a `_project_routing` that returned `None` unconditionally would
    pass every assertion in this module.
    """
    projected = _project_routing(_boundary())

    assert projected is not None
    assert projected.answer == "the page says forty-two."
    assert wobbles == []


def test_a_closed_enum_violation_names_the_offending_field(wobbles: list[dict[str, object]]) -> None:
    assert _project_routing(_boundary(shape="a shape the vocabulary does not have")) is None

    (fields,) = wobbles
    assert fields["boundary"] == "fetcher_routing_mirror"
    assert fields["field"] == "shape"
    assert fields["violating_fields"] == ["shape"]


def test_two_simultaneous_violations_are_both_named(wobbles: list[dict[str, object]]) -> None:
    """The defect the enricher fixes.

    The hand-rolled version read `errors()[0]` only, so a payload that broke two
    closed enums at once logged one field and the second was invisible — the
    operator fixes the named enum, re-runs, and the event fires again naming a
    field that was wrong the whole time.
    """
    assert _project_routing(_boundary(shape="not-a-shape", obstacle="not-an-obstacle")) is None

    (fields,) = wobbles
    assert sorted(fields["violating_fields"]) == ["obstacle", "shape"]  # ty: ignore[no-matching-overload]
    # `field` stays the first, so an existing operator grep on the singular key
    # keeps working; `violating_fields` is the addition, not a replacement.
    assert fields["field"] in {"shape", "obstacle"}


def test_unknown_is_reserved_for_a_non_validation_failure(wobbles: list[dict[str, object]]) -> None:
    """`"unknown"` must mean "not a ValidationError", not "a ValidationError I couldn't read".

    The `except` in `_project_routing` is deliberately broad, so this path is
    reachable: anything raised while BUILDING the dict (here, a boundary whose
    `other_pages` entry explodes on attribute access) lands in the same handler.
    """

    class _Exploding:
        url = "https://example.test/a"
        reason = "more"
        kind = "structural"

        @property
        def off_domain(self) -> bool:
            raise RuntimeError("not a ValidationError")

    assert _project_routing(_boundary(other_pages=(_Exploding(),))) is None

    (fields,) = wobbles
    assert fields["field"] == "unknown"
    assert fields["violating_fields"] == []
