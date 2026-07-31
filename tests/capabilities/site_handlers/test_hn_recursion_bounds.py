"""The HN comment tree is untrusted remote input and must be bounded.

`_render_kid` walked the Algolia `children` tree with no cap on either axis. The
tree arrives from the network, so its shape is not a2web's to assume: a thread
nested past CPython's ~1000-frame limit raised `RecursionError` straight out of
the handler. Not a degraded answer — an exception on the fetch path, from a
value a stranger controls.

Two failure modes, and the second is why a depth cap alone is not the fix:

1. **Plain nesting.** Every level is a real comment, so a depth cap bites.
2. **A chain of DELETED comments.** That branch recurses with `depth`
   UNCHANGED (a removed comment adds no blockquote level), so `_MAX_DEPTH` is
   never reached while the stack grows one frame per node. The shared comment
   budget is what bounds it.

Depth is the controlled variable here, which is the legitimate use of a
synthetic fixture — these are written in the real Algolia response shape
(`{"text", "author", "children"}`) so they cannot drift from what the parser
accepts.
"""

from __future__ import annotations

import pytest

from a2web.handlers.hn import _MAX_COMMENTS, _MAX_DEPTH, _render_item, _render_kid, _RenderBudget

# Comfortably past `sys.getrecursionlimit()` (1000) — the pre-fix code raised
# `RecursionError` on both shapes at this size.
_HOSTILE_DEPTH = 5000


def _nested_chain(levels: int, *, deleted: bool = False) -> dict:
    """A single chain `levels` deep, in the real Algolia child shape.

    `deleted=True` gives every node empty `text`, which is how the API reports a
    removed comment — the shape that defeats a depth cap.
    """
    node: dict = {"text": "leaf comment", "author": "leaf_author", "children": []}
    for i in range(levels):
        node = {
            "text": "" if deleted else f"comment body {i}",
            "author": f"user{i}",
            "children": [node],
        }
    return node


@pytest.mark.parametrize("deleted", [False, True], ids=["live-comments", "deleted-chain"])
def test_hostile_nesting_does_not_blow_the_stack(deleted: bool) -> None:
    """THE regression, both shapes. Pre-fix: `RecursionError`."""
    budget = _RenderBudget()
    rendered = _render_kid(_nested_chain(_HOSTILE_DEPTH, deleted=deleted), depth=1, budget=budget)

    assert isinstance(rendered, str)
    assert budget.truncated, "a bound was hit — it must be recorded, not silently absorbed"
    assert budget.remaining >= 0


def test_the_deleted_chain_is_bounded_by_the_comment_budget() -> None:
    """The depth cap alone would NOT have bounded this path.

    Deleted nodes do not advance `depth`, so `_MAX_DEPTH` is unreachable down a
    deleted chain. Asserting the budget is what drained proves the bound comes
    from the mechanism that actually applies here, rather than passing for a
    reason that would evaporate if the deleted branch changed.
    """
    budget = _RenderBudget()
    _render_kid(_nested_chain(_HOSTILE_DEPTH, deleted=True), depth=1, budget=budget)

    assert budget.remaining == 0, "the comment budget is the binding constraint on a deleted chain"


def test_depth_cap_bounds_a_live_thread() -> None:
    """A live thread stops at `_MAX_DEPTH` levels, well before the budget."""
    budget = _RenderBudget()
    rendered = _render_kid(_nested_chain(_HOSTILE_DEPTH), depth=1, budget=budget)

    deepest = max(len(line) - len(line.lstrip(">")) for line in rendered.splitlines() if line.startswith(">"))
    assert deepest <= _MAX_DEPTH, f"rendered {deepest} blockquote levels, cap is {_MAX_DEPTH}"
    assert budget.remaining > 0, "depth, not the budget, is what stopped a live chain"


def test_truncation_is_declared_in_the_render() -> None:
    """A bounded thread must say so — ADR-0009's honest-incompleteness floor.

    Without the notice the caller cannot distinguish "the thread ends here"
    from "a2web stopped rendering", and will read the former into the latter.
    """
    item = {
        "title": "A very deep thread",
        "author": "op",
        "children": [_nested_chain(_HOSTILE_DEPTH)],
    }
    content = _render_item(item)["content_md"]

    assert "truncated" in content.lower()
    assert str(_MAX_COMMENTS) in content and str(_MAX_DEPTH) in content, "the notice must name the bounds that applied"


def test_an_ordinary_thread_is_not_marked_truncated() -> None:
    """Anti-vacuity: if everything declared truncation the notice would be noise."""
    item = {
        "title": "A short thread",
        "author": "op",
        "children": [_nested_chain(3)],
    }
    content = _render_item(item)["content_md"]

    assert "truncated" not in content.lower()
    assert "comment body 0" in content, "non-vacuous: the thread must actually have rendered"
