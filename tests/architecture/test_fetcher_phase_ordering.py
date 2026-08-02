"""The four orderings inside the fetcher that are correct only because of WHERE they sit.

Written BEFORE `decompose-fetcher-into-files` cuts anything (task 1.4). Each of
these is a constraint that today lives as prose in a docstring, holds only by
statement position, and would survive a file move as a green test suite while
being silently broken — because every one of them is about ORDER, and no
behavioural test in this repo asserts order directly.

The guard indexes functions by NAME across the whole fetcher tree, whether that
is today's single `fetcher.py` or tomorrow's `fetcher/` package. That is
deliberate: a guard that resolves through an import would go quiet the moment a
function moved to a module that is no longer re-exported, which is exactly the
window the move opens.

Read `openspec/changes/decompose-fetcher-into-files/design.md` — "Anti-seams —
verified, do not cut these" — for why each one is load-bearing.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._walk import walked_files

_SRC = Path(__file__).resolve().parents[2] / "src" / "a2web"


def _fetcher_sources() -> list[Path]:
    """Every module of the fetcher, before or after the decomposition."""
    single = _SRC / "fetcher.py"
    if single.exists():
        return [single]
    return walked_files(_SRC / "fetcher", minimum=5)


def _index_functions() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map every top-level fetcher function name to its AST node.

    Collides loudly rather than silently: two functions of one name across the
    tree would make every ordering assertion below ambiguous, and picking one
    arbitrarily is how a guard starts inspecting the wrong body.
    """
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in _fetcher_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                assert node.name not in found, f"two fetcher functions named {node.name!r} — ordering assertions are ambiguous"
                found[node.name] = node
    return found


def _call_lines(node: ast.AST, name: str) -> list[int]:
    """Lines at which `name(...)` is called inside `node`."""
    lines: list[int] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == name:
            lines.append(sub.lineno)
    return lines


def _attribute_read_lines(node: ast.AST, obj: str, attr: str) -> list[int]:
    """Lines at which `obj.attr` is read inside `node`."""
    return [
        sub.lineno
        for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute)
        and sub.attr == attr
        and isinstance(sub.value, ast.Name)
        and sub.value.id == obj
    ]


def _require(fns: dict[str, ast.AST], *names: str) -> None:
    """Anti-vacuity floor: a renamed function must fail the test, not skip it."""
    missing = [n for n in names if n not in fns]
    assert not missing, (
        f"fetcher functions not found: {missing}. These guards pin ORDER, so a rename that "
        "goes unnoticed here leaves the ordering unguarded while the suite stays green — "
        "rename them here too, or state why the constraint retired."
    )


def test_the_escalation_win_check_precedes_the_won_tier_install() -> None:
    """`_phase_tier_loop`'s "an escalation already won" check reads a field the install writes.

    The check is `fc.tier_used != "none"` — it can only mean "an out-of-band
    escalation installed a win" because `_install_won_tier`, the other writer of
    that field, has NOT run yet at that point in the loop body. Move the install
    above the check and the condition becomes true for every winning tier, so the
    loop returns before it installs. Nothing else in the file says so.
    """
    fns = _index_functions()
    _require(fns, "_phase_tier_loop", "_install_won_tier")
    loop = fns["_phase_tier_loop"]

    checks = _attribute_read_lines(loop, "fc", "tier_used")
    installs = _call_lines(loop, "_install_won_tier")
    assert checks, "no `fc.tier_used` read in _phase_tier_loop — the escalation-win check moved or was renamed"
    assert installs, "no `_install_won_tier` call in _phase_tier_loop — the won-tier install moved"
    assert max(checks) < min(installs), (
        "the escalation-win check must read `fc.tier_used` BEFORE `_install_won_tier` writes it. "
        "Above the install the check is 'did an out-of-band escalation win'; below it, it is "
        "'did any tier win' — and the loop returns without installing."
    )


def test_the_terminal_floor_runs_after_both_promotions_and_after_the_answer() -> None:
    """The two promotions and the failure floor are one mutually-exclusive chain.

    `_apply_terminal` stands down on `fc.empty_confirmed` and on
    `fc.small_page_promoted()`, so it must run after both are decidable —
    and `small_page_promoted()` reads whether extraction produced an answer, so
    `_phase_extract_answer` has to sit between the small-page promotion and the
    floor. Reorder any of the three and ADR-0009's floor either fires on a
    promoted success or fails to fire on a real miss.

    `_apply_terminal` is called by the COORDINATOR, not the phase sequence, so
    it runs on the deadline path too. This asserts both halves.
    """
    fns = _index_functions()
    _require(
        fns,
        "_run_phases",
        "_run_pipeline",
        "_phase_complete_small_page_promotion",
        "_phase_extract_answer",
        "_phase_empty_promotion",
        "_apply_terminal",
    )
    phases = fns["_run_phases"]

    small_page = _call_lines(phases, "_phase_complete_small_page_promotion")
    answer = _call_lines(phases, "_phase_extract_answer")
    empty = _call_lines(phases, "_phase_empty_promotion")
    assert small_page and answer and empty, "the promotion/answer chain is no longer called from _run_phases"
    assert max(small_page) < min(answer), (
        "the small-page promotion must precede extraction — the flag is what UNLOCKS "
        "extraction on a thin body, so promoting afterwards promotes a page nothing read"
    )
    assert max(answer) < min(empty), (
        "the empty promotion must follow extraction — it runs after every escalation so the "
        "browser/subresource evidence `is_confirmed_empty` requires is already in the log"
    )

    assert not _call_lines(phases, "_apply_terminal"), (
        "`_apply_terminal` must NOT be called from _run_phases. The coordinator owns it so the "
        "never-silently-miss floor also runs on the DeadlineExceeded path; calling it in both "
        "places runs it twice on every successful fetch."
    )
    assert _call_lines(fns["_run_pipeline"], "_apply_terminal"), (
        "`_apply_terminal` is no longer called from the coordinator — ADR-0009's floor is off"
    )


def test_the_pre_rendered_branch_still_runs_the_ladder_and_the_sufficiency_check() -> None:
    """A pre-rendering tier has paid for extraction — it has NOT paid for the ladder.

    `_phase_extract`'s pre-rendered branch skips trafilatura, which is the whole
    optimisation. It must NOT skip `_run_extraction_escalation` (json/record
    synthesis over the same bytes, which no tier ran) or the sufficiency check.
    It did until 2026-07-28 — purely because those calls sat textually below the
    early return — and that starved four consumers on every fetch whose tier won
    with a pre-rendered payload: the candidate menu, `other_pages`, the listing
    record count, and the record set.

    The failure mode is an early return, so the assertion is that BOTH calls are
    reachable before every `return` in the branch.
    """
    fns = _index_functions()
    _require(fns, "_phase_extract", "_run_extraction_escalation", "_phase_listing_completeness")
    extract = fns["_phase_extract"]

    branch = next(
        (
            node
            for node in ast.walk(extract)
            if isinstance(node, ast.If)
            and any(
                isinstance(sub, ast.Attribute) and sub.attr == "pre_rendered_payload" for sub in ast.walk(node.test)
            )
        ),
        None,
    )
    assert branch is not None, "no `pre_rendered_payload` branch in _phase_extract — it moved or was renamed"

    ladder = _call_lines(branch, "_run_extraction_escalation")
    sufficiency = _call_lines(branch, "_phase_listing_completeness")
    assert ladder, (
        "the pre-rendered branch no longer runs the extraction ladder. Skipping it is not an "
        "optimisation — the ladder is json_in_html + record_mine, which no pre-rendering tier ran. "
        "See eval/findings_2026-07-28.md for the four consumers this starves."
    )
    assert sufficiency, "the pre-rendered branch no longer runs the sufficiency check — `listing_partial` can never fire on it"

    returns = [n.lineno for n in ast.walk(branch) if isinstance(n, ast.Return)]
    assert returns, "the pre-rendered branch no longer returns — this guard assumed an early-return shape"
    assert max(ladder + sufficiency) < min(returns), (
        "a `return` now precedes the ladder or the sufficiency check inside the pre-rendered "
        "branch. That is the exact 2026-07-28 defect: the calls existed, textually below the return."
    )


def test_every_escalation_that_installs_content_re_gates() -> None:
    """An escalation that installs new content and does not re-gate reports the OLD verdict.

    Not one of the design's four anti-seams — it is the invariant the loop
    restructure is meant to make structural, pinned here so the move cannot lose
    it on the way. Once escalation returns a retry signal instead of calling
    forward, this becomes redundant and should be deleted with a note, not left
    as decoration.
    """
    fns = _index_functions()
    _require(fns, "_escalate_browser", "_escalate_paid", "_install_gate_archive", "_regate_after_escalation")
    for name in ("_escalate_browser", "_escalate_paid"):
        assert _call_lines(fns[name], "_regate_after_escalation"), (
            f"{name} installs content without re-gating — the response would carry the verdict "
            "from before the escalation, which is a fetch reporting a wall it just got past"
        )
