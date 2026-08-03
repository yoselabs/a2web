"""Every site handler must be able to say that its parser stopped matching.

**Why this is a structural guard and not a review note.** Until 2026-08-03,
three of a2web's nine handlers could report parser rot and six could not. The
six did not fail loudly — they rendered a perfectly-formed result with
`Verdict.ok`:

    hn        `payload.get("hits", [])` -> `## Front page (0)`, ok
    v2ex      a 429 on the replies call -> the `## Replies` section vanishes, ok
    habr      a 429 on the comments call -> `## Discussion` vanishes, ok
    reddit    an unrecognised Atom `<id>` -> reported as "the thread was deleted"
    github    issue rows with rotted keys -> "this repo has no open issues"
    twitter   nitter markup moved -> `length_floor`, as if the tweet were thin

Each is ADR-0009's harm in its quietest form: a miss wearing the shape of an
answer. The cost is not hypothetical — a2web's arXiv and Wikipedia parsers were
both found returning ZERO rows against live pages holding 47 entries and 1066
anchors, each behind a green suite (2026-07-28). Detection came from a live
probe; the code itself said nothing.

**What this guard actually asserts** — deliberately weak, and the weakness is
the point. It asserts that every handler module *references* the one rot
reporter. It cannot assert the reference is placed correctly, or that it fires
on the right condition; a guard claiming that would be claiming more than an
AST walk can know. What it does buy is that a NEW handler cannot be merged with
no rot path at all, and that deleting the last report from an existing one goes
red. That is the failure mode that actually happened, nine times.

Pairs with `handler_probe.py`, which measures live yield against declared
floors. This guard says a handler *can* speak; the probe says whether what it
says is true.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

_HANDLERS = SRC_ROOT / "handlers"

#: Modules under `handlers/` that are not themselves site handlers.
_NOT_A_HANDLER = frozenset({"__init__.py", "_common.py"})

#: The one emitter. Named here rather than imported so the guard fails when the
#: helper is RENAMED as well as when it is dropped — an import would follow the
#: rename and keep passing.
_REPORTER = "report_rot"


def _handler_modules() -> list:
    return [p for p in walked_files(_HANDLERS, minimum=9) if p.name not in _NOT_A_HANDLER]


def test_every_handler_references_the_rot_reporter() -> None:
    silent = []
    for path in _handler_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        if _REPORTER not in names:
            silent.append(path.relative_to(SRC_ROOT).as_posix())

    assert not silent, (
        "These handlers have no way to report that their parser stopped "
        "matching the site:\n  " + "\n  ".join(silent) + "\n\n"
        f"Call `{_REPORTER}(...)` from `handlers/_common.py` on the branch "
        "where a load-bearing extraction comes back missing. Reporting does "
        "NOT decide the verdict — the handler still chooses whether to fail, "
        "drop an index, or mark a section. It only makes the rot observable.\n\n"
        "A handler that renders an empty-but-ok result when its parser dies is "
        "the ADR-0009 harm: a miss wearing the shape of an answer."
    )


def test_the_reporter_is_a_single_emitter() -> None:
    """`handler_schema_rot` is emitted from `_common.py` and nowhere else.

    One key, one call site, so an operator alerts on one thing and this guard's
    name-based check cannot be satisfied by a hand-rolled `log_warning` that
    drifts in shape.
    """
    offenders = []
    for path in walked_files(_HANDLERS, minimum=9):
        if path.name == "_common.py":
            continue
        if "handler_schema_rot" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(SRC_ROOT).as_posix())

    assert not offenders, (
        "The `handler_schema_rot` event literal appears outside `_common.py`:\n  "
        + "\n  ".join(offenders)
        + f"\n\nEmit it through `{_REPORTER}(...)` so there is exactly one "
        "producer of the key."
    )


def test_the_guard_can_actually_fail() -> None:
    """Mutation check — prove the walk sees handlers and would reject a silent one.

    Without this, a `_NOT_A_HANDLER` set that accidentally swallowed everything,
    or a `handlers/` path that stopped resolving, would leave both tests above
    green while checking nothing. `walked_files(minimum=...)` catches an empty
    tree; this catches an empty *filtered* tree, and confirms the AST check
    discriminates rather than always passing.
    """
    modules = _handler_modules()
    assert len(modules) >= 8, f"expected the nine site handlers, found {len(modules)}"

    # The check must REJECT a module with no reporter reference...
    empty = ast.parse("x = 1\n")
    assert _REPORTER not in {n.id for n in ast.walk(empty) if isinstance(n, ast.Name)}

    # ...and ACCEPT one with it, so it is not simply always-false.
    calls = ast.parse(f"{_REPORTER}('hn', missing=['hits'])\n")
    assert _REPORTER in {n.id for n in ast.walk(calls) if isinstance(n, ast.Name)}
