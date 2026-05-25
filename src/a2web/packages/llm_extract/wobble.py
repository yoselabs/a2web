"""Shared LLM-contract-parsing discipline.

Every site in the codebase that consumes LLM-returned JSON declares a per-field
`WobblePolicy`. The `apply_policy` helper resolves a parsed field against its
policy: STRICT raises on missing/invalid; DERIVE calls a per-field derive
callable and tags the result; DEFAULT substitutes; SKIP raises `WobbleSkip` so
the caller can short-circuit.

Every wobble (DERIVE / DEFAULT / SKIP recovery) fires the single structured log
event `llm_wobble` — operators grep one key across all four boundaries.

Lives under `packages/llm_extract/` and imports nothing from `a2web.<domain>`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

_LOG = structlog.get_logger("a2web.packages.llm_extract.wobble")

# Bound raw excerpts on the log so a huge payload doesn't bloat the log line.
_RAW_EXCERPT_MAX = 200


class WobbleTolerance(StrEnum):
    """Per-field policy for what to do when an LLM drops a JSON field.

    - STRICT: raise. The field is load-bearing; no recovery is meaningful.
    - DERIVE: call a per-field derive callable against `parsed`. Tags the
      verdict with a `_derived` marker so callers can audit recovered fields.
    - DEFAULT: substitute the `WobblePolicy.default` value. Used when the
      field is decorative (e.g. `reasoning`) and absence shouldn't drop the
      whole verdict.
    - SKIP: raise `WobbleSkip` so the caller can short-circuit to a known
      fallback (e.g. extractor returns `(text, None)` when routing is gone).
    """

    STRICT = "strict"
    DERIVE = "derive"
    DEFAULT = "default"
    SKIP = "skip"


@dataclass(slots=True, frozen=True)
class WobblePolicy:
    """One field's wobble-tolerance policy.

    `default` is meaningful only when `tolerance == DEFAULT`.
    `derive` is meaningful only when `tolerance == DERIVE`.
    """

    tolerance: WobbleTolerance
    default: Any = None
    derive: Callable[[dict[str, Any]], Any] | None = None


class WobbleSkip(Exception):
    """Raised by `apply_policy` when policy is SKIP and the field is missing.

    Caller catches and substitutes its short-circuit value (e.g. None or
    an empty tuple).
    """


def apply_policy(
    parsed: dict[str, Any],
    field: str,
    policy: WobblePolicy,
    *,
    boundary: str,
    model: str,
    raw_excerpt: str,
) -> Any:
    """Resolve `parsed[field]` against `policy`.

    Returns the resolved value. Raises `KeyError`/`TypeError` for STRICT
    misses (caller wraps in domain-specific ParseError). Raises `WobbleSkip`
    for SKIP misses.
    """
    present = field in parsed and parsed[field] is not None
    if present:
        return parsed[field]

    if policy.tolerance is WobbleTolerance.STRICT:
        raise KeyError(field)
    if policy.tolerance is WobbleTolerance.DERIVE:
        if policy.derive is None:
            raise KeyError(field)  # mis-declared policy — fail loud at runtime
        value = policy.derive(parsed)
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        return value
    if policy.tolerance is WobbleTolerance.DEFAULT:
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        return policy.default
    if policy.tolerance is WobbleTolerance.SKIP:
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        raise WobbleSkip(field)
    raise RuntimeError(f"unknown wobble tolerance: {policy.tolerance}")


def emit_wobble(
    *,
    boundary: str,
    field: str,
    tolerance: WobbleTolerance,
    model: str,
    raw_excerpt: str,
) -> None:
    """The single structured log event for every recovered LLM-contract wobble.

    Grep `llm_wobble` to find every site where a model dropped a field and the
    boundary recovered. `raw_excerpt` is bounded to keep log lines reasonable.
    """
    _LOG.warning(
        "llm_wobble",
        boundary=boundary,
        field=field,
        tolerance=tolerance.value,
        model=model,
        raw=raw_excerpt[:_RAW_EXCERPT_MAX] if raw_excerpt else "",
    )


__all__ = ("WobblePolicy", "WobbleSkip", "WobbleTolerance", "apply_policy", "emit_wobble")
