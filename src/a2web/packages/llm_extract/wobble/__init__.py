"""LLM-contract-parsing discipline — the typed funnel.

Every site that consumes LLM-returned JSON funnels through
`parse_with_policy` / `parse_list_with_policy`. The funnel:

  1. Strips ```json fences.
  2. `json.loads` — the ONLY legitimate call site inside `packages/llm_extract/`.
  3. Applies per-field `WobblePolicy` (STRICT raises, DERIVE/DEFAULT recover
     with an `llm_wobble` event).
  4. Constructs the typed payload and wraps it in `Wobbled`.

`Wobbled` is opaque — only the funnel constructs it. Downstream code typed as
`Wobbled` cannot accept a hand-rolled `RouterPayload`/dict fabricated outside,
making the bypass impossible without a deliberate type-ignore.

Pattern 1 of ADR-0001 (`docs/adr/0001-structural-prevention-over-vigilance.md`).
"""

from __future__ import annotations

from ._internal import (
    ParseError,
    Wobbled,
    WobblePolicy,
    WobbleSkip,
    WobbleTolerance,
    apply_policy,
    emit_wobble,
    parse_list_with_policy,
    parse_with_policy,
    recovered_fields,
    unwrap,
)
from ._policies import (
    BENCH_CLARITY_POLICY,
    BENCH_NEXT_LINKS_POLICY,
    EXTRACTOR_ROUTING_POLICY,
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
    "apply_policy",
    "emit_wobble",
    "parse_list_with_policy",
    "parse_with_policy",
    "recovered_fields",
    "unwrap",
)
