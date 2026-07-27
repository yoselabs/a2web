"""Every LLM test double SHALL declare — and prove — what it stands in for.

Four instruments in this repo have now reported success while measuring nothing:

  * 30 of 32 architecture tests passed against an EMPTY source tree
    (fixed by `_walk.walked_files(minimum=…)`)
  * `test_tools_return_pydantic_not_str` stayed green for a whole migration
    while matching `@a2kit.read`, a decorator that no longer existed
  * `_StubProvider` opened with `del system, user`, so every wire golden and
    most `query` capability tests silently ran the routing-LOST branch
  * `tests/eval_replay/harness.py` rebuilds `ExtractionResult` with no
    `routing=`, so all replayed eval cases run that same degraded branch

Each was found by accident, by someone looking for something else. The first
two are now covered by the non-vacuity floor and CLAUDE.md's "never add a
structural guard without an assertion that it found something". The last two
are a category that rule does not reach: TEST DOUBLES.

The cost is not hypothetical. The `_StubProvider` lie is why the ADR-0015
index-loss signal was measured as "fires on every query — permanent noise" and
shelved as blocked on a discriminator that never needed to exist. Live spikes
against a real provider later recovered the payload 15/15.

TWO LAYERS, because either alone is escapable:

  1. STATIC — every discovered double carries a `DOUBLES_ARM` declaration.
     Discovery is opt-OUT: a new double is caught by default, rather than
     relying on someone remembering to write a test for it. Remembering is
     what failed four times.

  2. BEHAVIOURAL — a double CLAIMING `ROUTER_FAITHFUL` is actually run against
     the real extractor and must produce a recoverable envelope. A declaration
     nobody checks is just a comment, and "this double is fine" was precisely
     the false belief.

This file is itself a structural guard, so it carries a floor and a
both-directions sensitivity case (see `test_the_check_rejects_a_contract_blind_double`
and `..._rejects_an_always_json_double`). Without the second, the check would
accept a fixture blind in the OPPOSITE direction — which is not hypothetical
either: the first patch to `_StubProvider` tested `"structural_form" in system`
where `system` is a *tuple* of prompt-cache blocks, so the membership test
compared elements and silently never matched.
"""

from __future__ import annotations

import ast
import inspect
import pkgutil
from pathlib import Path
from typing import Any

import pytest

from a2web.packages.llm_extract import EXTRACT_ROUTER_V1, Extractor, ModelSpec, ProviderResponse
from tests._helpers.llm_doubles import FIDELITY_FACTORY, DoubleArm

TESTS_ROOT = Path(__file__).resolve().parents[1]

#: Methods that make a class an LLM double. `complete` is the provider seam,
#: `extract` the extractor seam — the replay harness stubs the latter, which is
#: exactly why watching only the former would have missed it.
_DOUBLE_METHODS = frozenset({"complete", "extract"})

#: Floor, not a count. Twenty doubles exist today; well below that catches a
#: broken walk without tripping on ordinary deletions.
_MIN_DOUBLES = 15


class _Double:
    def __init__(self, name: str, path: Path, arm: str | None) -> None:
        self.name = name
        self.path = path
        self.arm = arm

    @property
    def where(self) -> str:
        return f"{self.path.relative_to(TESTS_ROOT.parent)}::{self.name}"


def _declared_arm(node: ast.ClassDef) -> str | None:
    """Read a literal `DOUBLES_ARM = ...` off the class body."""
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "DOUBLES_ARM":
                # `DoubleArm.X` or a bare string both acceptable to read; the
                # VALUE check below rejects anything not in the closed set.
                if isinstance(stmt.value, ast.Attribute):
                    return stmt.value.attr
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    return stmt.value.value
    return None


def _discover() -> list[_Double]:
    found: list[_Double] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if methods & _DOUBLE_METHODS:
                found.append(_Double(node.name, path, _declared_arm(node)))
    return found


def test_the_walk_is_not_vacuous() -> None:
    """A check that discovers nothing is indistinguishable from a passing one."""
    doubles = _discover()
    assert len(doubles) >= _MIN_DOUBLES, (
        f"LLM-double discovery found {len(doubles)}, expected at least {_MIN_DOUBLES}. "
        "Either the walk root moved (fix it) or the doubles were genuinely removed "
        "(lower the floor deliberately). An empty walk makes this guard decorative — "
        "which is the exact failure this file exists to prevent."
    )


def test_every_llm_double_declares_its_arm() -> None:
    """Undeclared blindness is the defect — not blindness itself."""
    undeclared = [d.where for d in _discover() if d.arm is None]
    assert not undeclared, (
        "These LLM test doubles do not declare `DOUBLES_ARM`:\n  "
        + "\n  ".join(sorted(undeclared))
        + "\n\nA double that ignores the contract it is handed cannot witness "
        "prompt-dependent behaviour. Declare what it stands in for using "
        "`tests/_helpers/llm_doubles.DoubleArm`. If it genuinely never reaches "
        "the router contract, `OFF_CONTRACT` is correct — but check that claim, "
        "because declaring it wrongly re-creates the original bug with a label on it."
    )


def test_declared_arms_are_in_the_closed_set() -> None:
    valid = {a.name for a in DoubleArm} | {a.value for a in DoubleArm}
    bad = [(d.where, d.arm) for d in _discover() if d.arm is not None and d.arm not in valid]
    assert not bad, f"Unknown DOUBLES_ARM values (closed set: {sorted(valid)}): {bad}"


# --------------------------------------------------------------------- #
# Layer 2 — the claim is verified, not taken on faith
# --------------------------------------------------------------------- #


def _router_faithful_doubles() -> list[tuple[str, Any]]:
    """Import the modules owning ROUTER_FAITHFUL doubles and return the classes.

    Doubles defined in THIS file are excluded: they are the check's own negative
    fixtures, deliberately built to fail, and are asserted against directly
    below. Including them in the population under test would make the suite
    permanently red for the wrong reason.
    """
    import importlib

    out: list[tuple[str, Any]] = []
    for d in _discover():
        if d.arm not in (DoubleArm.ROUTER_FAITHFUL.name, DoubleArm.ROUTER_FAITHFUL.value):
            continue
        if d.path == Path(__file__).resolve():
            continue
        rel = d.path.relative_to(TESTS_ROOT.parent).with_suffix("")
        mod = importlib.import_module(".".join(rel.parts))
        out.append((d.where, getattr(mod, d.name)))
    return out


def test_at_least_one_double_claims_router_fidelity() -> None:
    """Non-vacuity for layer 2 — otherwise the behavioural check tests nothing."""
    assert _router_faithful_doubles(), (
        "No double declares ROUTER_FAITHFUL, so the behavioural layer verifies nothing. "
        "The doubles backing the wire goldens and the `query` suite must claim it."
    )


@pytest.mark.asyncio
async def test_router_faithful_doubles_actually_satisfy_the_contract() -> None:
    """The claim is executed. A declaration nobody runs is a comment."""
    failures = []
    for where, cls in _router_faithful_doubles():
        factory = getattr(cls, FIDELITY_FACTORY, None)
        if factory is None:
            failures.append(f"{where}: claims ROUTER_FAITHFUL but has no `{FIDELITY_FACTORY}()`")
            continue
        double = factory()
        # Verify at whichever seam the double actually occupies. A provider
        # double is driven THROUGH the real extractor (so the real parse decides
        # the verdict, not the test); an extractor double IS the seam and is
        # asked directly. Checking only the provider seam would have missed the
        # replay harness, which is an extractor double — and missing it is how
        # 16 eval cases ran degraded without anyone noticing.
        if hasattr(double, "complete"):
            ex = Extractor(provider=double, model=ModelSpec("m"), template=EXTRACT_ROUTER_V1)
            result = await ex.extract(content="page content", ask="what?", request_routing=True)
        else:
            result = await double.extract(content="page content", ask="what?", request_routing=True)
        if result.routing is None:
            failures.append(f"{where}: claims ROUTER_FAITHFUL but the envelope was not recoverable")
    assert not failures, "\n".join(failures)


@pytest.mark.asyncio
async def test_router_faithful_doubles_are_contract_SENSITIVE() -> None:
    """Fidelity is answering the contract given — not always answering the same way.

    A double hard-wired to emit an envelope regardless of the prompt passes the
    check above while being exactly as blind as the version it replaced, just
    failing in the opposite direction. So each faithful double is ALSO driven on
    a non-routing contract and must NOT produce a routing payload.

    This is the substance of the deleted per-double
    `test_stub_provider_fidelity.py`: subsuming it must not lose the assertion,
    only the duplication. Applying it to every double rather than one is
    strictly stronger than what was removed.
    """
    from a2web.packages.llm_extract import TERSE_V1

    failures = []
    for where, cls in _router_faithful_doubles():
        double = getattr(cls, FIDELITY_FACTORY)()
        if not hasattr(double, "complete"):
            continue  # extractor-seam doubles have no prompt to be sensitive to
        ex = Extractor(provider=double, model=ModelSpec("m"), template=TERSE_V1)
        result = await ex.extract(content="page content", ask="what?")  # routing NOT requested
        if result.routing is not None:
            failures.append(
                f"{where}: produced a routing payload when none was requested — it is insensitive to the contract, not faithful to it."
            )
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------- #
# The check's own sensitivity — BOTH directions
# --------------------------------------------------------------------- #


class _ContractBlindDouble:
    """The original bug, preserved: ignores the prompt entirely."""

    DOUBLES_ARM = DoubleArm.UNPARSABLE

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system, user
        return ProviderResponse(text="prose, no envelope", model=model, prompt_tokens=1, completion_tokens=1, cost_usd=0.0, latency_ms=1)

    @classmethod
    def for_fidelity_check(cls) -> _ContractBlindDouble:
        return cls()


class _AlwaysJsonDouble:
    """Blind in the OPPOSITE direction: emits an envelope even when none was asked for.

    Declared ROUTER_FAITHFUL because on the ROUTER path it genuinely is — the
    behavioural layer passes it. Its defect shows only on the NON-router path,
    which is the point of the sensitivity case below and the reason that case
    cannot be dropped.
    """

    DOUBLES_ARM = DoubleArm.ROUTER_FAITHFUL

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system, user
        return ProviderResponse(
            text='{"answer": "a", "structural_form": "article", "shape": "prose"}',
            model=model,
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            latency_ms=1,
        )

    @classmethod
    def for_fidelity_check(cls) -> _AlwaysJsonDouble:
        return cls()


@pytest.mark.asyncio
async def test_the_check_rejects_a_contract_blind_double() -> None:
    """A prompt-blind double must NOT be able to claim router fidelity."""
    ex = Extractor(provider=_ContractBlindDouble(), model=ModelSpec("m"), template=EXTRACT_ROUTER_V1)
    result = await ex.extract(content="c", ask="q", request_routing=True)
    assert result.routing is None, (
        "A double that discards `system`/`user` produced a recoverable envelope — "
        "the fidelity check can no longer tell a faithful double from a blind one."
    )


@pytest.mark.asyncio
async def test_the_check_rejects_an_always_json_double() -> None:
    """Insensitive-to-contract is a failure too, not just insensitive-to-routing.

    Without this case, a double hard-wired to always emit an envelope would sail
    through the fidelity check while being exactly as blind as the version it
    replaced — failing in the opposite direction.
    """
    from a2web.packages.llm_extract import TERSE_V1

    ex = Extractor(provider=_AlwaysJsonDouble(), model=ModelSpec("m"), template=TERSE_V1)
    result = await ex.extract(content="c", ask="q")  # no routing requested
    assert result.answer.lstrip().startswith("{"), (
        "The always-JSON double is supposed to leak raw JSON on the NON-routing path; "
        "if it no longer does, this sensitivity case has stopped discriminating."
    )


def test_helper_module_is_importable_and_closed() -> None:
    """Guards against the vocabulary silently growing an un-reviewed arm."""
    assert {a.value for a in DoubleArm} == {
        "router_faithful",
        "unparsable",
        "unclassified",
        "provider_error",
        "off_contract",
    }, "DoubleArm changed — a new arm needs a matching verification story, not just an enum member."


def _unused_keep_imports() -> None:  # pragma: no cover - import anchors
    _ = (inspect, pkgutil)
