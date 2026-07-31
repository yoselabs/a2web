"""Every per-request network bound is operator-reachable.

Fourteen request timeouts were frozen as module constants — `twitter` 5s through
`zyte` 60s — with no way for an operator to move any of them. A deployment on a
slow link, or in a region far from the origin, had no knob at all.

The knob is a SCALE (`request_timeout_scale`), not fourteen absolute overrides
and not one flat value. Those numbers are individually tuned and their RATIOS
carry the meaning: a paid server-side render legitimately needs 6x what an
nitter probe does. Fourteen knobs would be a second copy of the table that
drifts from the first; one flat value would erase the tuning and cap the paid
render at the probe's budget.

This guard is structural because the failure mode is a site left behind: a new
tier, or a new fetch inside an existing one, that goes back to reading the bare
constant. That reads as fine and is invisible until an operator's setting
mysteriously does not apply to one hop.
"""

from __future__ import annotations

import ast

from a2web.settings import AppSettings

from ._walk import SRC_ROOT, walked_files

_ROOTS = (SRC_ROOT / "tiers", SRC_ROOT / "handlers")

# Names holding a per-request network bound.
_BOUND_NAMES = frozenset({"_TIMEOUT_S", "_DEFAULT_TIMEOUT_S"})

# Below the current population, far above zero.
_MIN_FILES = 6
# 14 sites were routed; a floor well under that catches a broken walk.
_MIN_ROUTED = 8


def _bare_constant_uses(tree: ast.Module) -> list[str]:
    """Uses of a bound constant that are NOT inside a `request_timeout(...)` call.

    The constant is still the source of truth for the site's tuned value — it
    is *passed to* `request_timeout`. What must not survive is handing it
    straight to a network call, which is the shape that ignores the operator.
    """
    scaled: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "request_timeout":
            for arg in ast.walk(node):
                if isinstance(arg, ast.Name):
                    scaled.add(id(arg))

    bare: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _BOUND_NAMES and id(node) not in scaled:
            # An assignment (`_TIMEOUT_S = 10.0`) is the declaration, not a use.
            if isinstance(node.ctx, ast.Store):
                continue
            bare.append(f"line {node.lineno}: {node.id}")
    return bare


def test_no_request_bound_bypasses_the_operator_scale() -> None:
    routed = 0
    offenders: list[str] = []

    for root in _ROOTS:
        for path in walked_files(root, minimum=_MIN_FILES):
            source = path.read_text(encoding="utf-8")
            if not any(name in source for name in _BOUND_NAMES):
                continue
            tree = ast.parse(source)
            routed += source.count("request_timeout(")
            for use in _bare_constant_uses(tree):
                offenders.append(f"{path.name}:{use}")

    assert routed >= _MIN_ROUTED, f"non-vacuous: expected at least {_MIN_ROUTED} scaled bounds, found {routed}"
    assert not offenders, (
        f"request bound(s) not routed through `settings.request_timeout(...)`: {offenders}. "
        "An operator's `A2WEB_REQUEST_TIMEOUT_SCALE` silently will not apply to these hops. "
        "Pass the constant through `state.settings.request_timeout(...)`, or thread the "
        "resolved value in where `state` is out of scope (see archive/habr/v2ex/github)."
    )


def test_the_scale_actually_moves_a_bound() -> None:
    """The knob must compute, not merely exist."""
    assert AppSettings().request_timeout(10) == 10
    assert AppSettings(request_timeout_scale=2.0).request_timeout(10) == 20
    assert AppSettings(request_timeout_scale=0.5).request_timeout(60) == 30


def test_the_scale_preserves_the_ratios() -> None:
    """The whole reason it is a scale: relative tuning survives.

    A flat override would cap the paid render at the probe's budget, which is
    the bug the shape exists to avoid.
    """
    scaled = AppSettings(request_timeout_scale=3.0)
    twitter, zyte = scaled.request_timeout(5), scaled.request_timeout(60)
    assert zyte / twitter == 12, "the 5s:60s ratio must survive scaling"


def test_the_scale_cannot_be_set_to_something_dangerous() -> None:
    """Bounded both ways: 0 would disable every bound, 100x would push a single
    hop past the whole fetch deadline."""
    import pytest
    from pydantic import ValidationError

    for bad in (0, -1, 50):
        with pytest.raises(ValidationError):
            AppSettings(request_timeout_scale=bad)
