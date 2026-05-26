# Design — wobble-typed-funnel

## Scope

Pattern 1 of ADR-0001. Make `wobble.parse_with_policy` the only legitimate constructor of an opaque `Wobbled` NewType; migrate four canonical sites; rely on `ty` for cooperative consumers and on a pytest-archon `json.loads`-ban (landed by `arch-fitness-functions-bootstrap`) as the structural backstop.

## Architecture

```
                  Today                              Proposed
   ┌──────────────────────────┐    ┌──────────────────────────────┐
   │ extractor._split_*       │    │ extractor._split_*           │
   │   json.loads(...)        │    │   parse_with_policy(         │
   │   isinstance gauntlet    │    │     raw,                     │
   │   silent recovery        │    │     policies=_ROUTING,       │
   │   no llm_wobble emit ✗   │    │     into=RouterPayload,      │
   └──────────────────────────┘    │     boundary=...,            │
                                   │     model=...,               │
   ┌──────────────────────────┐    │   ) → Wobbled                │
   │ judge.parse_verdict      │    └──────────────────────────────┘
   │   apply_policy(...)      │                  │
   │   semi-conforming        │                  ▼
   └──────────────────────────┘    ┌──────────────────────────────┐
                                   │ wobble/__init__.py           │
   ┌──────────────────────────┐    │   Wobbled NewType            │
   │ bench_judge._parse_*     │    │   parse_with_policy ← funnel │
   │   apply_policy(...)      │    │   unwrap[T](w, expected=T)   │
   │   semi-conforming        │    │                              │
   └──────────────────────────┘    │ wobble/_internal.py          │
                                   │   _Parsed[T] (private)       │
   ┌──────────────────────────┐    │   _apply_field (private)     │
   │ fetcher_response.        │    │                              │
   │   _project_routing       │    │ wobble/_policies.py          │
   │   manual llm_wobble emit │    │   _ROUTING / _NEXT_LINKS /   │
   └──────────────────────────┘    │   _VERDICT / _CLARITY        │
                                   └──────────────────────────────┘
                                              ▲
                          ┌───────────────────┴───────────────────┐
                          │ ONLY place in packages/llm_extract/   │
                          │ that calls json.loads                 │
                          │ Enforced by pytest-archon (see        │
                          │ arch-fitness-functions-bootstrap)     │
                          └───────────────────────────────────────┘
```

## Decisions

### D1 — `Wobbled` is a `NewType`, not a generic class

```python
Wobbled = NewType("Wobbled", _Parsed[Any])
```

Two alternatives rejected:

- **Generic class `Wobbled[T](Generic[T])`** — would allow `Wobbled[RouterPayload]` annotations. Costs: extra runtime indirection, more complex type-narrowing at consumer sites. Benefit (parametric annotation) is achievable via `unwrap[T](w, *, expected=T) -> T` which type-narrows at the unwrap site.
- **Phantom-types / `Phantom` subclass** — runtime enforcement, requires `phantom-types` + `beartype` deps. Rejected per ADR-0001 ("LARP boundary explicitly avoided"). Reconsider only if wobble migrates into `a2kit`.

The chosen `NewType` is structurally `_Parsed[Any]` at runtime — bypass would require constructing `_Parsed` directly, which is `_-prefixed private` (convention) and additionally banned by archon (mechanical).

### D2 — `into=` is `Callable[..., T]`, accepts both dataclasses and pydantic

```python
def parse_with_policy[T](
    raw: str, *,
    policies: dict[str, WobblePolicy],
    into: Callable[..., T],  # dataclass.__init__ OR BaseModel.model_validate
    ...
) -> Wobbled: ...
```

`Callable[..., T]` works for both `RouterPayload(**resolved)` (frozen dataclass at the package boundary) and `BaseModel.model_validate(resolved)` (pydantic at the domain seam). Each consumer passes the appropriate callable.

Rejected: type-introspection (`if isinstance(into, BaseModel-subclass)`). Adds magic; consumer site is explicit about its target shape.

### D3 — `parse_with_policy` owns `json.loads` AND fence-stripping

Today's split: `_strip_fences` lives inline in each caller; `json.loads` lives inline in each caller; `apply_policy` is a helper. After: all three concentrate in the funnel. Rationale: the archon rule bans `json.loads` outside the funnel; if `_strip_fences` stayed outside, callers would still need to do the fence-strip + json.loads dance, defeating the funnel.

### D4 — `unwrap` requires an `expected` type witness

```python
def unwrap[T](w: Wobbled, *, expected: type[T]) -> T:
    """Type-narrow the wrapped value. Raises TypeError on mismatch."""
```

Two alternatives rejected:

- **`unwrap(w) -> Any`** — cheap but punts on type safety at the seam. Defeats the funnel.
- **`unwrap(w) -> T` via generic var capture** — pyright supports this in some cases; cross-checker portability is shaky (`ty` is still maturing).

The `expected=` kwarg is explicit and survives any type-checker. Slight verbosity at consumer sites; one-line tradeoff per call.

### D5 — Per-boundary policy tables live in `_policies.py`, not in consumer modules

Today: each consumer module declares its own policy table (`_JUDGE_POLICY`, `_CLARITY_POLICY`, `_NEXT_LINKS_POLICY`). After: all five tables centralised in `wobble/_policies.py`. Consumers `from .._policies import EXTRACTOR_ROUTING_POLICY` (or similar).

Rationale: a future "show me all wobble policies in the codebase" audit is one file open. New parse sites must add their policy table next to the existing ones, making "is this site wobble-aware?" a single-file check rather than a grep.

Cost: slight coupling between the funnel package and each consumer's exact field list. Acceptable — the field list is part of the LLM-prompt contract, which itself lives in `packages/llm_extract/prompts.py` (a sibling).

### D6 — `apply_policy` is retired from public surface

Currently exported from `packages/llm_extract/__init__.py`. After: `_apply_field` lives in `wobble/_internal.py`, called only by `parse_with_policy`. The public surface shrinks: `parse_with_policy`, `unwrap`, `Wobbled`, `WobblePolicy`, `WobbleTolerance`, `WobbleSkip`, `emit_wobble`.

`emit_wobble` stays public *only* for sites that need to emit a wobble event outside of parsing (none today; reserved for future). If after migration nothing imports `emit_wobble`, retire it too.

### D7 — `fetcher_response._project_routing` accepts `Wobbled[RouterPayload]`

Today: takes `RouterPayload | None` (the loose boundary type) and manually emits `llm_wobble` on closed-enum violations. After: takes `Wobbled[RouterPayload]`, unwraps once, projects to the strict pydantic mirror. The wobble events for closed-enum violations *also* funnel through `parse_with_policy` — the projection itself becomes a policy table on the strict-mirror constructor.

**Resolved during step 6 (2026-05-26 implementation):** `_project_routing` does NOT call `json.loads`. Its only input is `RouterBoundary | None` from `ExtractionResult.routing`, set exclusively by `Extractor.extract` which itself funnels through `parse_with_policy`. The bypass is structurally blocked at the upstream `_split_answer_and_routing` boundary. `_project_routing` keeps its current shape (manual `llm_wobble` emit on pydantic ValidationError for closed-enum violations); the archon `json.loads`-ban passes trivially because this function never calls it. Plumbing `Wobbled[RouterPayload]` end-to-end would require widening `ExtractionResult.routing` and rippling through every consumer for no security gain.

## Migration order

1. Build the new `wobble/` folder side-by-side with `wobble.py` (don't delete the old surface yet).
2. Migrate `_split_answer_and_routing` first — biggest gain, exercises the funnel against the most complex policy table.
3. Migrate `_split_answer_and_next_links` — same pattern, simpler.
4. Migrate `judge.parse_verdict` — already wobble-aware; shape change is small.
5. Migrate `bench_judge._parse_clarity` + `_parse_next_links` — same.
6. Adapt `fetcher_response._project_routing` to accept `Wobbled[RouterPayload]`.
7. Delete `wobble.py`; update `__init__.py` exports.
8. Tests: green at each step. Final `make check` covers the funnel.

The `arch-fitness-functions-bootstrap` change lands AFTER step 7 — the archon rule depends on the new folder layout.

## Risk register

- **R1 — `Wobbled` annotation drift.** If a downstream helper takes `Any` and accepts an unwrapped `RouterPayload`, the funnel claim weakens. Mitigation: archon rule (later change), code review checklist, the `unwrap(w, *, expected=T)` shape that makes unwrap-site explicit.
- **R2 — Pydantic projection-via-policy might not fit cleanly.** If D7's open question resolves to "no", `_project_routing` keeps a smaller bespoke wobble emit. The funnel claim narrows to "JSON parsing", which is still the dominant smell.
- **R3 — `ty` immaturity around `NewType`.** Verify during step 1 that `ty` flags a type mismatch when a bare `RouterPayload` is passed where `Wobbled` is expected. If not, fall back to `pyright` for the type-check gate (the project already runs `make ty`).
