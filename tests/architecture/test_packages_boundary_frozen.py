"""Architectural invariant: boundary dataclasses under `packages/` are frozen.

Boundary types — the ones domain code reads at the package seam — must be
immutable. A mutable boundary lets a domain caller pretend to mutate package
state through a value object, which is exactly the leak the packages-
independence rule exists to prevent.

This test walks the boundary modules and asserts each named dataclass is
`@dataclass(frozen=True, ...)`. Phase 7 of `fetcher-orchestrator-refactor-v1`.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

import pytest

from a2web.packages.block_detector import BlockResult
from a2web.packages.browser_backends import BackendCookie, RenderedPage
from a2web.packages.content_extract import ExtractedContent, ExtractedHeading, ExtractedLink
from a2web.packages.escalation import EscalationSignal

# NB: CacheRow and CookieRow left `packages/` when the cache and cookie-store
# primitives were promoted to the shelf (`http_cache`, `browser_cookies`); their
# freeze is now the shelf's invariant, so they drop off this list.

_FROZEN_BOUNDARY_TYPES = (
    ExtractedHeading,
    ExtractedLink,
    ExtractedContent,
    BlockResult,
    EscalationSignal,
    BackendCookie,
    RenderedPage,
)


@pytest.mark.parametrize("cls", _FROZEN_BOUNDARY_TYPES)
def test_boundary_dataclass_is_frozen(cls: type) -> None:
    assert is_dataclass(cls), f"{cls.__name__} should be a dataclass"
    # The frozen flag lives at __dataclass_params__.frozen on the class.
    params = getattr(cls, "__dataclass_params__", None)
    assert params is not None, f"{cls.__name__} has no __dataclass_params__"
    assert params.frozen, f"{cls.__name__} must be @dataclass(frozen=True)"
    # Sanity: slots present too (a separate but related discipline).
    assert "__slots__" in cls.__dict__ or hasattr(cls, "__slots__"), f"{cls.__name__} should use slots=True"


def test_no_default_dataclass_carries_runtime_setattr() -> None:
    """A frozen dataclass raises FrozenInstanceError on field set — confirms
    the freeze actually applies at runtime (not just at type-check time)."""
    from dataclasses import FrozenInstanceError

    signal = EscalationSignal(next_tier="browser", reason="js_required")
    with pytest.raises(FrozenInstanceError):
        signal.next_tier = "archive"  # type: ignore[misc]

    # ExtractedContent has required positional fields, but a FrozenInstanceError
    # on any field set on a constructed instance proves the freeze.
    sample = ExtractedContent(content_md="x")
    with pytest.raises(FrozenInstanceError):
        sample.content_md = "y"  # type: ignore[misc]

    # Use field names from the actual schema to keep the assertion robust if
    # the dataclass gains fields later.
    assert all(fields(cls) for cls in _FROZEN_BOUNDARY_TYPES)
