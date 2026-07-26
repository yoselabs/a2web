"""a2web's binding of the shelf `llm-wobble` funnel.

The funnel machinery — fence stripping, `json.loads`, per-field `WobblePolicy`
application, the opaque `Wobbled` token — lives in the shelf package
`llm_wobble` (promoted from this module 2026-07-26). a2web keeps only two things
here:

  - the product POLICY TABLES (`_policies.py`) — which fields each a2web envelope
    requires and how each recovers;
  - this thin binding, which injects a2web's single managed `a2web` logger so
    every `llm_wobble` recovery event drains through a2web's sinks (the MCP-stdio
    single-channel discipline) instead of the package's default logger.

Boundary-safe: the logger is resolved by NAME via stdlib `logging`, so this
module under `packages/` never imports `a2web.<domain>` (tach.toml / the
independence test). The `_policies` re-export keeps every existing consumer's
`from .wobble import EXTRACTOR_ROUTING_POLICY` import working unchanged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

import llm_wobble as _w
from llm_wobble import (
    ParseError,
    Wobbled,
    WobblePolicy,
    WobbleSkip,
    WobbleTolerance,
    recovered_fields,
    unwrap,
)

from ._policies import (
    BENCH_CLARITY_POLICY,
    BENCH_NEXT_LINKS_POLICY,
    EXTRACTOR_ROUTING_POLICY,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Any

T = TypeVar("T")

# Resolved by name — NOT `from a2web.log import ...` — so `packages/` stays free
# of domain imports. Same logger object `a2web.log.configure()` manages.
_A2WEB_LOGGER = logging.getLogger("a2web")


def parse_with_policy(
    raw: str,
    *,
    policies: Mapping[str, WobblePolicy],
    into: Callable[[dict[str, Any]], T],
    boundary: str,
    model: str,
    logger: logging.Logger | None = None,
) -> Wobbled:
    """`llm_wobble.parse_with_policy` with a2web's managed logger injected."""
    return _w.parse_with_policy(raw, policies=policies, into=into, boundary=boundary, model=model, logger=logger or _A2WEB_LOGGER)


def parse_list_with_policy(
    raw: str,
    *,
    item: Callable[[dict[str, Any]], T | None],
    boundary: str,
    model: str,
    strip_fences: bool = True,
    logger: logging.Logger | None = None,
) -> Wobbled:
    """`llm_wobble.parse_list_with_policy` with a2web's managed logger injected."""
    return _w.parse_list_with_policy(
        raw, item=item, boundary=boundary, model=model, strip_fences=strip_fences, logger=logger or _A2WEB_LOGGER
    )


def emit_wobble(
    *,
    boundary: str,
    field: str,
    tolerance: WobbleTolerance,
    model: str,
    raw_excerpt: str,
    logger: logging.Logger | None = None,
) -> None:
    """`llm_wobble.emit_wobble` with a2web's managed logger injected."""
    _w.emit_wobble(
        boundary=boundary, field=field, tolerance=tolerance, model=model, raw_excerpt=raw_excerpt, logger=logger or _A2WEB_LOGGER
    )


__all__ = (
    "BENCH_CLARITY_POLICY",
    "BENCH_NEXT_LINKS_POLICY",
    "EXTRACTOR_ROUTING_POLICY",
    "ParseError",
    "WobblePolicy",
    "WobbleSkip",
    "WobbleTolerance",
    "Wobbled",
    "emit_wobble",
    "parse_list_with_policy",
    "parse_with_policy",
    "recovered_fields",
    "unwrap",
)
