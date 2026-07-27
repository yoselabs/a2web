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

from llm_wobble import (
    ParseError,
    Wobbled,
    WobblePolicy,
    WobbleSkip,
    WobbleTolerance,
    bind,
    recovered_fields,
    strip_fenced_blocks,
    unwrap,
)

from ._policies import (
    BENCH_CLARITY_POLICY,
    BENCH_NEXT_LINKS_POLICY,
    EXTRACTOR_ROUTING_POLICY,
)

# Resolved by name — NOT `from a2web.log import ...` — so `packages/` stays free
# of domain imports. Same logger object `a2web.log.configure()` manages.
_A2WEB_LOGGER = logging.getLogger("a2web")

# `bind` rather than three hand-written wrapper functions, which is what this
# module used to be. A wrapper restates the signature it wraps, so a parameter
# added upstream silently stops reaching a2web's call sites — the same drift
# that let the replay harness quietly stop passing `routing=`. `bind` is
# `functools.partial` underneath: one binding, no second signature to rot.
_funnel = bind(_A2WEB_LOGGER)

parse_with_policy = _funnel.parse_with_policy
parse_list_with_policy = _funnel.parse_list_with_policy
emit_wobble = _funnel.emit_wobble


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
    "strip_fenced_blocks",
    "unwrap",
)
