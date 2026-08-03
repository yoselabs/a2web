"""The hazards the rejected Stage protocol would have made unexpressible.

`decompose-fetcher-into-files` design D4 rejected a `Stage` protocol — a typed
per-stage input/output contract — on the grounds that it buys ceremony and not
much safety, and committed to a tripwire: *write the one architecture test that
covers the residual hazards, and if it proves hard to write, reopen the
decision.* This file is that test. It was not hard to write, so the decision
stands.

Three hazards, from `tasks.md` §5.1. Each is a property that holds today by
convention — statement position, or the absence of a clearing branch — and that
a Stage protocol would have carried in its signature instead.

**They are guarded, not fixed.** Two of the three are open behaviour changes
filed in `BACKLOG.md`; this change's rule is that the only behaviour change is
the ladder-skip fix (D7). What a guard buys on an OPEN hazard is that its blast
radius cannot grow silently — a fifth paid claimant, or a second field that
survives re-comprehension, has to come here and say so.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._walk import walked_files

_SRC = Path(__file__).resolve().parents[2] / "src" / "a2web"


def _fetcher_functions() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every top-level fetcher function, by name, across the tree."""
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in [*walked_files(_SRC / "fetcher", minimum=5), _SRC / "actions" / "playbook.py"]:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                assert node.name not in found, f"two fetcher functions named {node.name!r}"
                found[node.name] = node
    return found


def _calls(node: ast.AST) -> set[str]:
    """Names called inside `node`, bare or through a module attribute."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                out.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                out.add(fn.attr)
    return out


def _reachable(fns: dict[str, ast.AST], root: str) -> set[str]:
    """Transitive closure of calls from `root`, restricted to fetcher functions."""
    seen = {root}
    frontier = [root]
    while frontier:
        for name in _calls(fns[frontier.pop()]) & fns.keys():
            if name not in seen:
                seen.add(name)
                frontier.append(name)
    return seen


# ---------------------------------------------------------------------------
# Hazard 1 — the paid budget is resolved by call order.


#: The four claimants, in the precedence `paid_budget_available`'s docstring
#: states. The order here is the PHASE order and therefore the answer to "who
#: gets the one paid dispatch"; changing it is a behaviour change with its own
#: change, not an edit to this list.
#:
#: Three of the four ask `paid_budget_available(fc)`. The fourth cannot: the
#: planner rule lives in `actions/playbook.py`, the pure module BOTH sides
#: import, so it can see the cap but not the fetcher-side predicate. It asks the
#: same `PAID_DISPATCH_CAP` against its own `PlannerCaps` snapshot — which is
#: the honest structural answer, and is why this table records HOW each claimant
#: asks rather than assuming one spelling.
_PAID_CLAIMANTS = {
    "_phase_gate_and_escalate": "paid_budget_available",
    "_decide_paid_last_resort": "PAID_DISPATCH_CAP",
    "_obstacle_wants_render": "paid_budget_available",
    "_listing_wants_render": "paid_budget_available",
}


def test_the_paid_budget_is_claimed_through_one_predicate() -> None:
    """Four independent `paid_dispatches < 1` tests were four chances to disagree.

    The cap is single-sited now (`PAID_DISPATCH_CAP`) and every claimant asks
    the same predicate, so the precedence is readable in one docstring instead
    of being an emergent property of phase order. That is worth guarding for the
    `NEXT_LINKS_CAP` reason: one stated invariant with six implementations
    shipped five times the cap while a probe recorded the violation as healthy.

    Two halves, and the second is the anti-rot one: every name the docstring
    lists must exist and must actually call the predicate. A precedence list
    that has stopped describing real callers reads as a decision while being
    decoration — the `test_every_accepted_delta_is_real` failure mode.
    """
    fns = _fetcher_functions()
    assert "paid_budget_available" in fns, "the paid-budget predicate is gone — the cap is back to N literals"

    strays = sorted(
        name
        for name, node in fns.items()
        if name != "paid_budget_available"
        for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute)
        and sub.attr == "paid_dispatches"
        and isinstance(sub.ctx, ast.Load)
        and isinstance(sub.value, ast.Name)
        and sub.value.id == "fc"
        if name not in {"_escalate_paid", "_planner_caps"}
    )
    assert not strays, (
        f"{strays} read `fc.paid_dispatches` directly. Ask `paid_budget_available(fc)` — a second "
        "reader is a second place the cap and the precedence can drift apart."
    )

    missing = [c for c in _PAID_CLAIMANTS if c not in fns]
    assert not missing, f"the precedence docstring names claimants that no longer exist: {missing}"
    silent = sorted(
        name
        for name, asks in _PAID_CLAIMANTS.items()
        if asks not in _calls(fns[name]) and asks not in {n.id for n in ast.walk(fns[name]) if isinstance(n, ast.Name)}
    )
    assert not silent, (
        f"{silent} are listed as paid claimants but no longer ask for the budget the way this table "
        "says. Either they stopped claiming it (drop them here and from the docstring) or they went "
        "back to a literal, which is the eleven-copies state this collapsed."
    )


# ---------------------------------------------------------------------------
# Hazard 2 — a field written only on success survives re-comprehension.


#: Fields a SECOND comprehension pass can leave holding the FIRST pass's value:
#: written somewhere inside comprehension, and never assigned a clearing
#: constant (`None` / `False`) on any path. The escalation loop (§3.2) made this
#: routine — `escalate` re-runs the ladder over the newly installed body, so a
#: body that yields no records leaves the previous body's count in place.
#:
#: `_phase_listing_completeness`'s `items_loaded` / `items_total` / `items_more`
#: are deliberately NOT here: §3.4 gave that function a symmetric clear, which
#: is exactly the shape this ledger is the absence of.
#:
#: Each entry says whether the stickiness is INTENDED.
_SURVIVES_RECOMPREHENSION = {
    # Intended. "A later stage may ADD to an index, never silently replace it" —
    # the handler knows the site, the miner is guessing from shape.
    "next_links_handler": "intended — producer-claim precedence, CLAUDE.md `Never`",
    "record_set": "intended — same rule; the JSON fallback fills only when the structural path found nothing",
    # NOT intended, both filed in BACKLOG.md rather than fixed here (a clearing
    # branch is a behaviour change, and this change ships one).
    "record_count": "OPEN — a re-comprehension that finds no records leaves the old count, which "
    "`_phase_listing_completeness` then assesses against the NEW page's oracle total",
    "regex_oracle_total": "OPEN — set only when a numeric oracle matched, never cleared; a second "
    "pass over a page with no oracle keeps the first total, and `_apply_llm_listing_oracle` "
    "stands down on exactly that field, so the LLM superset silently declines to fire",
}

#: A write is a CLEAR when it assigns one of these. Anything else is a set.
_CLEARING = (None, False)


def test_every_field_that_survives_re_comprehension_is_declared() -> None:
    """Enumerated, not latent — a third sticky field has to come here and say so.

    The hazard is not that these fields are sticky; two of the three are sticky
    on purpose, and the ledger says which. The hazard is that stickiness is
    invisible at the write site: `if x: fc.f = ...` with no `else` reads as an
    ordinary assignment, and only the loop restructure made the second pass
    routine enough for the difference to matter.

    A Stage protocol would have made this unexpressible by handing each stage a
    fresh output object. Absent that, the substitute is that the set is closed.
    """
    fns = _fetcher_functions()
    assert "_comprehend" in fns, "`_comprehend` is gone — the re-comprehension seam this guard covers no longer exists"

    written: dict[str, set[str]] = {}
    refreshed: set[str] = set()
    for name in _reachable(fns, "_comprehend"):
        node = fns[name]
        unconditional = {id(stmt) for stmt in node.body}
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            # Either shape means the field is re-derived, not carried: an
            # assignment the function always executes, or one that puts the
            # field back to its unset value.
            renews = id(sub) in unconditional or (isinstance(sub.value, ast.Constant) and any(sub.value.value is c for c in _CLEARING))
            for tgt in sub.targets:
                if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "fc":
                    written.setdefault(tgt.attr, set()).add(name)
                    if renews:
                        refreshed.add(tgt.attr)

    assert written, (
        "no `fc.<field> =` write found anywhere reachable from `_comprehend`. That is not plausible — "
        "the walk stopped resolving, so this guard is inspecting nothing."
    )
    assert refreshed, (
        "no re-derived write found either. The renewal discrimination is what separates a sticky "
        "field from one recomputed on every pass; if it matches nothing, every field below is a "
        "false positive and the ledger is measuring the wrong thing."
    )

    sticky = {f: srcs for f, srcs in written.items() if f not in refreshed}
    undeclared = sorted(set(sticky) - set(_SURVIVES_RECOMPREHENSION))
    assert not undeclared, (
        f"undeclared fields that survive re-comprehension: {undeclared} "
        f"(written in {sorted({s for f in undeclared for s in sticky[f]})}). "
        "`escalate` re-runs comprehension over the newly installed body, so a field with no clearing "
        "write on any path keeps the PREVIOUS body's value. Give it a clear, or declare it in "
        "`_SURVIVES_RECOMPREHENSION` with why the stickiness is correct."
    )

    stale = sorted(set(_SURVIVES_RECOMPREHENSION) - set(sticky))
    assert not stale, (
        f"{stale} are declared sticky but now have a clearing write (or left comprehension entirely). "
        "Drop them — a ledger entry that describes nothing reads as a decision."
    )


# ---------------------------------------------------------------------------
# Hazard 3 — the gate-archive install diverging from its pre-gate sibling.


def test_the_gate_archive_install_cannot_diverge_from_its_sibling() -> None:
    """Subsumed by the chokepoint, asserted here so §5.1's third hazard is closed.

    `_install_gate_archive` did not set `fc.status_code` while
    `_install_archive_payload` always did — two archive paths disagreeing for no
    reason anybody chose. The omission was INERT (§2.4: `status_code` has one
    reader, and cache_write declines archive results), so this is a trap
    disarmed rather than a bug fixed. It is unexpressible now only because both
    go through `install`, which writes every field `TierInstall` declares.

    `test_transport_install_chokepoint.py` owns the general rule; this pins the
    specific pair the task named, so the hazard is closed by name.
    """
    fns = _fetcher_functions()
    for site in ("_install_gate_archive", "_install_archive_payload"):
        assert site in fns, f"{site} is gone — §5.1's third hazard needs restating against whatever replaced it"
        assert "install" in _calls(fns[site]), (
            f"{site} no longer routes through `install`. Hand-writing the transport fields is how the "
            "two archive paths came to disagree; the chokepoint writes all six or none."
        )
