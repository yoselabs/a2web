"""Wobble internals — policy primitives, the typed funnel, fence stripping.

Public surface is re-exported from `__init__.py`. Nothing inside this module
should be imported directly by consumers; the funnel API is the contract.

Pattern 1 of ADR-0001 (`docs/adr/0001-structural-prevention-over-vigilance.md`):
`Wobbled` is the opaque NewType wrapping `_Parsed`. The only legitimate
constructor is `parse_with_policy` / `parse_list_with_policy` inside this
module — downstream code typed as `Wobbled` cannot accept a bare
`RouterPayload` / dict / etc. fabricated by a hand-rolled `json.loads` path.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, NewType, TypeVar

# Package-pure: emit directly on the stdlib `a2kit` logger (governed by
# a2kit's LogConfig) rather than importing the domain `a2web.log` helper —
# `packages/` may not import from `a2web.<domain>`.
_LOG = logging.getLogger("a2kit")

_RAW_EXCERPT_MAX = 200

T = TypeVar("T")


class WobbleTolerance(StrEnum):
    """Per-field policy for what to do when an LLM drops a JSON field."""

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
    """Raised when a SKIP-policy field is missing — caller short-circuits."""


class ParseError(Exception):
    """The raw envelope failed JSON decode, isn't a dict/list, or violates a
    STRICT policy. Callers translate to their boundary-specific error type.
    """


@dataclass(frozen=True, slots=True)
class _Parsed(Generic[T]):
    """Private payload — constructed only inside this module."""

    value: T
    recovered_fields: tuple[str, ...]


Wobbled = NewType("Wobbled", _Parsed[Any])


def unwrap(w: Wobbled) -> Any:
    """Extract the wrapped value. Caller's local annotation narrows the type."""
    return w.value  # type: ignore[attr-defined]


def recovered_fields(w: Wobbled) -> tuple[str, ...]:
    """Names of fields that fell back to DERIVE/DEFAULT/SKIP recovery."""
    return w.recovered_fields  # type: ignore[attr-defined]


def _strip_fences(text: str) -> str:
    """Strip optional ```...``` (or ```json...```) markdown fences."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body.startswith("json"):
        body = body[4:]
    if "```" in body:
        body = body.split("```", 1)[0]
    return body.strip()


def emit_wobble(
    *,
    boundary: str,
    field: str,
    tolerance: WobbleTolerance,
    model: str,
    raw_excerpt: str,
) -> None:
    """Single structured log event for every recovered LLM-contract wobble."""
    _LOG.warning(
        "llm_wobble",
        extra={
            "a2kit_fields": {
                "boundary": boundary,
                "field": field,
                "tolerance": tolerance.value,
                "model": model,
                "raw": raw_excerpt[:_RAW_EXCERPT_MAX] if raw_excerpt else "",
            }
        },
    )


def _apply_field(
    parsed: dict[str, Any],
    field: str,
    policy: WobblePolicy,
    *,
    boundary: str,
    model: str,
    raw_excerpt: str,
) -> tuple[Any, bool]:
    """Resolve `parsed[field]` against `policy`.

    Returns `(value, recovered)`. `recovered=True` iff a wobble was emitted.
    Raises `KeyError`/`TypeError` for STRICT misses, `WobbleSkip` for SKIP.
    """
    present = field in parsed and parsed[field] is not None
    if present:
        return parsed[field], False

    if policy.tolerance is WobbleTolerance.STRICT:
        raise KeyError(field)
    if policy.tolerance is WobbleTolerance.DERIVE:
        if policy.derive is None:
            raise KeyError(field)
        value = policy.derive(parsed)
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        return value, True
    if policy.tolerance is WobbleTolerance.DEFAULT:
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        return policy.default, True
    if policy.tolerance is WobbleTolerance.SKIP:
        emit_wobble(boundary=boundary, field=field, tolerance=policy.tolerance, model=model, raw_excerpt=raw_excerpt)
        raise WobbleSkip(field)
    raise RuntimeError(f"unknown wobble tolerance: {policy.tolerance}")


def apply_policy(
    parsed: dict[str, Any],
    field: str,
    policy: WobblePolicy,
    *,
    boundary: str,
    model: str,
    raw_excerpt: str,
) -> Any:
    """Back-compat shim for the legacy direct-call surface.

    Internal new code should funnel through `parse_with_policy` instead.
    """
    value, _ = _apply_field(parsed, field, policy, boundary=boundary, model=model, raw_excerpt=raw_excerpt)
    return value


def parse_with_policy(
    raw: str,
    *,
    policies: Mapping[str, WobblePolicy],
    into: Callable[[dict[str, Any]], T],
    boundary: str,
    model: str,
) -> Wobbled:
    """Strip fences → `json.loads` → apply per-field policy → call `into(resolved_dict)`.

    The only legitimate constructor of `Wobbled` for object envelopes.
    Raises `ParseError` on malformed JSON / wrong root type / STRICT miss.
    `WobbleSkip` propagates so callers can short-circuit.
    """
    stripped = _strip_fences(raw)
    try:
        parsed = json.loads(stripped)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ParseError(f"{boundary}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ParseError(f"{boundary}: expected JSON object, got {type(parsed).__name__}")

    resolved: dict[str, Any] = {}
    recovered: list[str] = []
    for field, policy in policies.items():
        try:
            value, was_recovered = _apply_field(parsed, field, policy, boundary=boundary, model=model, raw_excerpt=raw)
        except KeyError as exc:
            raise ParseError(f"{boundary}: missing required field: {exc}") from exc
        resolved[field] = value
        if was_recovered:
            recovered.append(field)

    # Surface any non-policied fields too — callers may want them for raw inspection.
    for k, v in parsed.items():
        resolved.setdefault(k, v)

    value_out = into(resolved)
    return Wobbled(_Parsed(value=value_out, recovered_fields=tuple(recovered)))


def parse_list_with_policy(
    raw: str,
    *,
    item: Callable[[dict[str, Any]], T | None],
    boundary: str,
    model: str,
    strip_fences: bool = True,
) -> Wobbled:
    """Strip fences (optional) → `json.loads` → expect list → filter via `item(...)`.

    For envelopes where the model returns a JSON array (extractor's next_links
    block). `item(dict) -> T | None` returns None to silently drop malformed
    entries; that filtering happens inside the funnel, not in caller code.

    Returns a `Wobbled` wrapping `list[T]`. `recovered_fields` lists the
    indices (as strings) of dropped entries.
    """
    payload = _strip_fences(raw) if strip_fences else raw.strip()
    try:
        parsed = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ParseError(f"{boundary}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ParseError(f"{boundary}: expected JSON array, got {type(parsed).__name__}")

    out: list[T] = []
    dropped: list[str] = []
    for idx, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            dropped.append(str(idx))
            continue
        entry_dict = {str(k): v for k, v in entry.items()}
        result = item(entry_dict)
        if result is None:
            dropped.append(str(idx))
            continue
        out.append(result)
    if dropped:
        emit_wobble(
            boundary=boundary,
            field=f"items[{','.join(dropped)}]",
            tolerance=WobbleTolerance.DEFAULT,
            model=model,
            raw_excerpt=raw,
        )
    return Wobbled(_Parsed(value=out, recovered_fields=tuple(dropped)))


__all__ = (
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
