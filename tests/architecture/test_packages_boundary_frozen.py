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
from a2web.packages.escalation import EscalationSignal

# NB: CacheRow, CookieRow, and the ExtractedContent/Heading/Link trio left
# `packages/` when the cache, cookie-store, and content-extract primitives were
# promoted to the shelf (`http_cache`, `browser_cookies`, `content_extract`);
# their freeze is now the shelf's invariant, so they drop off this a2web list.

_FROZEN_BOUNDARY_TYPES = (
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

    # Every frozen boundary type still carries fields (guards an empty tuple).
    assert all(fields(cls) for cls in _FROZEN_BOUNDARY_TYPES)
