"""The frozen preamble and the bound resources are inputs, not pipeline state.

**This guard changed shape once the refactor it guarded actually landed, and
the before/after is the interesting part.**

Before `decompose-fetcher-into-files` §7.2, the 19 fields now in `FetchInputs`
and `FetchResources` sat flat on `FetchContext`, a mutable slotted dataclass.
Nothing stopped a phase assigning one; the only assurance was this file walking
`src/` for `fc.<name> = ...` and finding none. That was the strongest thing a
static walk could honestly say, and it was deliberately written BEFORE the lift
— a guard written after a refactor proves the refactor happened, one written
before proves it is still possible.

The lift landed, so the property is now enforced by the language: both classes
are `frozen=True`, and assigning a field raises `FrozenInstanceError` at
runtime. There is nothing left for a walk to discover.

**So what is left to assert is that the freeze is still there.** `frozen=True`
is one keyword. Deleting it is a one-character-class edit that breaks no test,
changes no behaviour on any passing path, and silently restores the mutable bag
this change existed to remove. That is exactly the kind of regression this repo
keeps finding, so it gets an assertion rather than a comment.

The membership half survives too: a field moving back out of the frozen pair
onto `FetchContext` would be the same regression wearing a different hat, and
`ty` has nothing to say about where a field lives.
"""

from __future__ import annotations

import ast
import dataclasses

import pytest

from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources

from ._walk import SRC_ROOT

#: The preamble — fixed before the pipeline starts, constant for its duration.
#: Note these are NOT all "the caller's": `started_at`, `start_perf`,
#: `deadline_perf` and `profile_hash` are computed inside `fetch()`. What unites
#: them is lifetime, not provenance, which is why the class is `FetchInputs`
#: and not `FetchRequest`.
_EXPECTED_INPUTS = frozenset(
    {
        "ask",
        "bypass_cache",
        "deadline_perf",
        "debug",
        "include_links",
        "include_routing",
        "link_roles",
        "max_content_chars",
        "next_links_enabled",
        "profile_hash",
        "requested_url",
        "start_perf",
        "started_at",
        "wrap_content",
    }
)

#: The injected resources. Freezing these carries a reason beyond tidiness:
#: rebinding one mid-fetch would mean a single fetch talking to two different
#: browsers, or writing to a different cache than it read from.
_EXPECTED_RESOURCES = frozenset(
    {
        "browser_backend",
        "browser_robust_backend",
        "cookie_jar",
        "llm_extractor",
        "sqlite",
    }
)


@pytest.mark.parametrize("cls", [FetchInputs, FetchResources], ids=lambda c: c.__name__)
def test_the_bundle_is_frozen(cls: type) -> None:
    """The keyword that does all the work."""
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen, (
        f"`{cls.__name__}` is no longer `frozen=True`.\n"
        "That keyword IS the invariant: without it these become ordinary mutable "
        "fields again and a phase can rebind an input or a resource mid-fetch. For a "
        "resource specifically, that means one fetch talking to two different browsers "
        "or writing to a different cache than it read from."
    )


@pytest.mark.parametrize("cls", [FetchInputs, FetchResources], ids=lambda c: c.__name__)
def test_the_freeze_actually_raises(cls: type) -> None:
    """Mutation-proof the assertion above against the real runtime.

    `__dataclass_params__.frozen` is metadata. This is the behaviour, which is
    what a phase would actually hit — and it fails if a future `__setattr__`
    override ever made the metadata a lie.
    """
    instance = _an_instance(cls)
    target = next(iter(sorted(f.name for f in dataclasses.fields(cls))))
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, target, None)


def test_the_two_bundles_hold_exactly_the_lifted_fields() -> None:
    """Membership, which `ty` cannot speak to.

    A field moved back onto `FetchContext` type-checks perfectly and quietly
    rejoins the mutable bag. Each set is asserted exactly — a field appearing in
    neither, or in both, is a real question rather than a detail.
    """
    assert {f.name for f in dataclasses.fields(FetchInputs)} == _EXPECTED_INPUTS
    assert {f.name for f in dataclasses.fields(FetchResources)} == _EXPECTED_RESOURCES

    on_context = {f.name for f in dataclasses.fields(FetchContext)}
    leaked = sorted((_EXPECTED_INPUTS | _EXPECTED_RESOURCES) & on_context)
    assert not leaked, (
        f"these were lifted into the frozen bundles but are declared on `FetchContext` again: {leaked}.\n"
        "A field in both places is worse than in neither — readers and writers will "
        "disagree about which one is authoritative."
    )


def test_the_context_reaches_them_only_through_the_bundles() -> None:
    """No compatibility shim quietly re-flattens the boundary.

    A `@property def debug(self): return self.inputs.debug` on `FetchContext`
    would make every call site work again and undo the decomposition without
    touching a single test. It is the obvious next "helpful" edit, so it is
    named here rather than discovered later.
    """
    tree = ast.parse((SRC_ROOT / "fetcher" / "context.py").read_text(encoding="utf-8"))
    cls = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "FetchContext")
    accessors = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}

    shims = sorted(accessors & (_EXPECTED_INPUTS | _EXPECTED_RESOURCES))
    assert not shims, (
        f"`FetchContext` defines accessor(s) re-exposing lifted field(s): {shims}.\n"
        "Read them through `fc.inputs.<name>` / `fc.resources.<name>`. A forwarding "
        "property restores the flat surface and the decomposition with it."
    )


def _an_instance(cls: type) -> object:
    if cls is FetchResources:
        return FetchResources()
    from datetime import UTC, datetime

    return FetchInputs(started_at=datetime.now(UTC), start_perf=0.0, profile_hash="x", bypass_cache=True)
