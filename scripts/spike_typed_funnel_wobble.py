"""SPIKE — Typed funnel for wobble.py (Recipe A from explore session 2026-05-26).

NOT a production change. NOT importable from a2web. Sketch only — measures
LOC + cognitive load of routing `_split_answer_and_routing` through a typed
funnel vs the current 78-line hand-rolled parser.

Compare:
  - CURRENT — src/a2web/packages/llm_extract/extractor.py:346-423 (78 lines).
    Hand-rolls json.loads + isinstance gauntlet. Silent recovery on optional
    fields. Does NOT emit llm_wobble events.
  - PROPOSED — see _split_answer_and_routing_v2 below (~25 lines).
    Routes through `parse_with_policy`. Every recovered optional emits
    llm_wobble automatically. Bypass becomes a type error: downstream code
    typed as Wobbled[RouterPayload] cannot accept a bare RouterPayload.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, NewType, TypeVar

T = TypeVar("T")


# ---- PROPOSED FUNNEL API ---------------------------------------------------
#
# Lives in packages/llm_extract/wobble/__init__.py (folder-package today is
# a single wobble.py; this spike assumes promotion to a folder so we can
# split _internal.py from the public surface).
#
# The funnel is the ONLY place in packages/llm_extract/ allowed to call
# json.loads. Enforced by pytest-archon (Pattern 3).


@dataclass(frozen=True, slots=True)
class _Parsed(Generic[T]):
    """Private: only constructed inside the wobble module."""

    value: T
    recovered_fields: tuple[str, ...]


# Opaque NewType — downstream code accepts Wobbled[T], can't fabricate one.
Wobbled = NewType("Wobbled", _Parsed[Any])


class ParseError(Exception):
    """Malformed envelope (not recoverable via policy)."""


def parse_with_policy(
    raw: str,
    *,
    policies: dict[str, Any],  # would be dict[str, WobblePolicy] in real code
    into: Callable[..., T],
    boundary: str,
    model: str,
) -> Wobbled:
    """The ONLY entry point. Strips ``` fences, json.loads, applies per-field
    policies, constructs `into(**resolved)`, wraps in Wobbled."""
    stripped = _strip_fences(raw)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ParseError(f"{boundary}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ParseError(f"{boundary}: expected object, got {type(parsed).__name__}")

    resolved: dict[str, Any] = {}
    recovered: list[str] = []
    for field, policy in policies.items():
        # Real impl delegates to existing apply_policy(); spike stubs:
        if field in parsed and parsed[field] is not None:
            resolved[field] = parsed[field]
        else:
            resolved[field] = _stub_recover(field, policy, recovered)

    return Wobbled(_Parsed(value=into(**resolved), recovered_fields=tuple(recovered)))


def unwrap(w: Wobbled) -> Any:
    """Extract the wrapped value. Type-narrowed at use site to T."""
    return w[0].value  # _Parsed is structural at runtime; this is internal


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        body = stripped[3:]
        if body.startswith("json"):
            body = body[4:]
        if "```" in body:
            body = body.split("```", 1)[0]
        return body.strip()
    return stripped


def _stub_recover(field, policy, recovered):
    # Stand-in for apply_policy; emits llm_wobble in real impl
    recovered.append(field)
    return None


# ---- PROPOSED REWRITE OF _split_answer_and_routing ------------------------
#
# Compare against extractor.py:346-423 (78 lines).


# Stand-in for the real RouterPayload boundary type:
@dataclass(frozen=True, slots=True)
class RouterPayload:
    answer: str
    structural_form: str
    shape: str
    genre: str | None = None
    obstacle: str | None = None
    ask_here: tuple[str, ...] = ()
    try_url: tuple[Any, ...] = ()


# Stand-in for WobblePolicy enums:
class WobbleTolerance:
    STRICT = "strict"
    DEFAULT = "default"


_ROUTING_POLICIES = {
    "answer": WobbleTolerance.STRICT,
    "structural_form": WobbleTolerance.STRICT,
    "shape": WobbleTolerance.STRICT,
    "genre": WobbleTolerance.DEFAULT,  # default=None
    "obstacle": WobbleTolerance.DEFAULT,  # default=None
    "ask_here": WobbleTolerance.DEFAULT,  # default=()
    "try_url": WobbleTolerance.DEFAULT,  # default=()
}


def _split_answer_and_routing_v2(text: str, *, model: str) -> tuple[str, RouterPayload | None]:
    """13 LOC (down from 78). Wobble events fire automatically on optional misses."""
    try:
        wobbled = parse_with_policy(
            text,
            policies=_ROUTING_POLICIES,
            into=RouterPayload,
            boundary="extractor.router_shape",
            model=model,
        )
    except (ParseError, KeyError, TypeError):
        return text, None
    payload: RouterPayload = unwrap(wobbled)
    return payload.answer, payload


# ---- WHAT TYPE CHECKING CATCHES ------------------------------------------
#
# Today: downstream sites accept `RouterPayload | None`. A new helper can
# happily do `json.loads(raw)` + manual dict.get() and feed the result in.
# pyright/ty sees nothing wrong.
#
# With this spike: downstream sites accept `Wobbled` (or `Wobbled` unwrapped
# into RouterPayload by the consumer). A hand-rolled parser returns a bare
# RouterPayload, and the type checker flags it at every call site that
# expects Wobbled.
#
# pytest-archon (Pattern 3) closes the laundering gap: ANY `json.loads` call
# inside packages/llm_extract/ outside wobble/ fails CI, even if the result
# is typed as Any.


def _demonstrate_bypass_caught() -> None:
    """This function would FAIL ty's type check under the proposed funnel."""

    def downstream_consumer(payload: Wobbled) -> str:
        """Typed as Wobbled — only legitimately constructable via parse_with_policy."""
        return unwrap(payload).answer

    # The bypass path:
    raw_dict = json.loads('{"answer": "...", "structural_form": "...", "shape": "..."}')
    bypass = RouterPayload(**raw_dict)
    # downstream_consumer(bypass)  # ← ty would flag: expected Wobbled, got RouterPayload


if __name__ == "__main__":
    print("Spike sketch only — not meant to be executed.")
    print(__doc__)
