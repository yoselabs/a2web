"""The caller's request and the injected resources are inputs, not pipeline state.

`FetchContext` carries 75 fields and reads as one mutable bag, which is why
`decompose-fetcher-into-files` phase two looked so much harder than it is.
Surveying it (2026-08-03, recorded in that change's §7.2) found that **18 of
those fields are never written by any pipeline node** — they are the caller's
arguments plus the injected `Lazy[T]` resources, set once at construction in
`fetcher/__init__.py` and read thereafter.

They are not context state at all. Lifting them into a frozen request/resources
pair is phase two's largest self-contained win, and this guard is its
precondition: the lift is safe and mechanical exactly as long as nothing
assigns them mid-fetch. Measured zero such assignments across `src/a2web` when
this was written.

**Pinned BEFORE the lift, deliberately.** A guard written after a refactor
proves the refactor happened; a guard written before it proves the refactor is
possible, and goes red the moment someone makes it impossible. If a future
phase needs to mutate one of these, that is a real design decision — this test
is where it surfaces, rather than being discovered halfway through the cut.

**What it does not claim.** It does not say these fields are immutable at
runtime — `FetchContext` is a mutable slotted dataclass and Python will happily
assign any of them. It says no code in `src/` does. That is the property the
lift needs, and it is the strongest one a static walk can honestly assert.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

#: The caller's own parameters — everything `fetch()` was asked for.
_REQUEST_PARAMS = frozenset(
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
        "started_at",
        "wrap_content",
    }
)

#: The injected resources. `Lazy[T]` thunks plus the shared sqlite handle —
#: passed down UNAWAITED so cold start stays cheap (see
#: `test_cold_start_laziness.py`), and rebinding one mid-fetch would mean a
#: single fetch talking to two different browsers or two different caches.
_INJECTED_RESOURCES = frozenset(
    {
        "browser_backend",
        "browser_robust_backend",
        "cookie_jar",
        "llm_extractor",
        "sqlite",
    }
)

_FROZEN = _REQUEST_PARAMS | _INJECTED_RESOURCES

#: Names a `FetchContext` is bound to across the tree. `self` covers writes from
#: inside `context.py`'s own methods, which is where an "innocent" mutation
#: would most plausibly be added.
_CONTEXT_BINDINGS = frozenset({"fc", "ctx", "self"})


def _assignments_to(tree: ast.AST) -> list[ast.Attribute]:
    """Every `<binding>.<frozen field> = ...` in one module.

    Covers plain, augmented and annotated assignment. `AugAssign` matters more
    than it looks: `fc.deadline_perf -= x` is a mutation that a naive search for
    `= ` would miss entirely.
    """
    out: list[ast.Attribute] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        out.extend(
            t
            for t in targets
            if isinstance(t, ast.Attribute) and t.attr in _FROZEN and isinstance(t.value, ast.Name) and t.value.id in _CONTEXT_BINDINGS
        )
    return out


def test_no_pipeline_code_writes_the_request_or_its_resources() -> None:
    violations: list[str] = []
    for path in walked_files(SRC_ROOT, minimum=80):
        for node in _assignments_to(ast.parse(path.read_text(encoding="utf-8"))):
            binding = node.value.id  # type: ignore[union-attr]
            violations.append(f"{path.relative_to(SRC_ROOT).as_posix()}:{node.lineno}  {binding}.{node.attr}")

    assert not violations, (
        "A request parameter or injected resource is assigned after construction:\n  "
        + "\n  ".join(violations)
        + "\n\nThese 18 fields are inputs, not pipeline state — set once in "
        "`fetcher/__init__.py` and read thereafter. Two consequences if that stops "
        "being true: `decompose-fetcher-into-files` §7.2 can no longer lift them "
        "into a frozen request/resources pair, and for a resource specifically, one "
        "fetch could end up talking to two different browsers or two different "
        "caches.\n\nIf the mutation is genuinely needed, move the field out of the "
        "set above and say why — do not delete the assertion."
    )


def test_every_frozen_field_is_really_on_the_context() -> None:
    """The set cannot outlive the fields it names.

    Without this, renaming `wrap_content` would leave a guard silently watching
    a field that no longer exists — still green, still counting itself as
    coverage, protecting nothing. It is the same failure the `_READS` ledger
    had before `ResponseContext` replaced it, and the reason that replacement
    needed a separate existence check bolted on.
    """
    tree = ast.parse((SRC_ROOT / "fetcher" / "context.py").read_text(encoding="utf-8"))
    cls = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "FetchContext")
    declared = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}

    assert len(declared) >= 50, f"non-vacuous: parsed only {len(declared)} FetchContext fields"
    missing = sorted(_FROZEN - declared)
    assert not missing, (
        f"these names are guarded as request-frozen but are not fields on `FetchContext`: {missing}.\n"
        "A guard naming something that does not exist reads as coverage while providing none."
    )


def test_the_detector_can_actually_fire() -> None:
    """Mutation check — prove the walk would catch each assignment form.

    The walk over real source finds zero violations, which is indistinguishable
    from a detector that finds nothing ever. Each form is checked separately
    because `AugAssign` and `AnnAssign` are separate AST nodes and an earlier
    draft handled only `Assign`.
    """
    for src in ("fc.debug = True", "fc.deadline_perf -= 1", "fc.sqlite: object = None", "self.wrap_content = False"):
        assert _assignments_to(ast.parse(src)), f"detector missed {src!r}"

    for src in ("fc.content_md = 'x'", "other.debug = True", "debug = True", "x = fc.debug"):
        assert not _assignments_to(ast.parse(src)), f"detector wrongly flagged {src!r}"
