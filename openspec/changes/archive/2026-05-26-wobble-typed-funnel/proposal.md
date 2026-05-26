# wobble-typed-funnel

## Why

`wobble.py` declares a contract-parsing discipline. CLAUDE.md claims "four canonical sites today" route every LLM-JSON parse through `apply_policy` and emit a single `llm_wobble` log key. In practice only two do.

The two non-conforming sites:

- `packages/llm_extract/extractor.py:346-423` — `_split_answer_and_routing` (78 LoC). The largest LLM-JSON parser in the codebase. Calls `json.loads` directly, hand-rolls `isinstance` + `.get()` gauntlet, silently recovers missing optional fields without emitting `llm_wobble`. Operators have no signal when the model drops `genre` / `obstacle` / `ask_here` / `try_url`.
- `fetcher_response.py:45-94` (`_project_routing`) — calls `apply_policy` for closed-enum projection but does its own pre-checks; mixed shape.

The discipline is bypassable because it's a *helper kit*, not a *funnel*. Per ADR-0001 (Pattern 1), the fix is to make `wobble.parse_with_policy` the only legitimate constructor of an opaque `Wobbled` NewType, type every downstream consumer to accept `Wobbled[T]`, and let `ty` / `pyright` flag bypass at edit time. Backstop: a pytest-archon rule (added by the `arch-fitness-functions-bootstrap` change) banning `json.loads` calls anywhere in `packages/llm_extract/` outside `wobble/`.

This change is the *proof of pattern* — smallest blast radius, validates that the typed-funnel idiom survives `make check`, `ty`, and the production hot path. The other two ADR-0001 changes build on the precedent set here.

## What changes

### `packages/llm_extract/wobble.py` → `packages/llm_extract/wobble/` (folder package)

The flat module becomes a folder with split public / private surface:

```
packages/llm_extract/wobble/
  __init__.py     — only public exports (Wobbled, parse_with_policy, unwrap,
                    WobblePolicy, WobbleTolerance, WobbleSkip, emit_wobble)
  _internal.py    — _Parsed dataclass, _apply_field (current apply_policy
                    body), _strip_fences helper. Not exported.
  _policies.py    — Per-boundary policy tables (extractor router-shape,
                    extractor next-links, judge verdict, bench-judge clarity,
                    bench-judge next-links). Each consumer imports its table
                    by name from here, NOT defines its own locally.
```

### New public surface

```python
# wobble/__init__.py
T = TypeVar("T")
Wobbled = NewType("Wobbled", _Parsed[Any])  # opaque, only constructable via parse_with_policy

def parse_with_policy(
    raw: str,
    *,
    policies: dict[str, WobblePolicy],
    into: Callable[..., T],   # dataclass ctor or BaseModel.model_validate
    boundary: str,            # for llm_wobble event tagging
    model: str,               # ditto
) -> Wobbled: ...

def unwrap[T](w: Wobbled, *, expected: type[T]) -> T: ...  # type-narrowing helper
```

`parse_with_policy` is the **only** place inside `packages/llm_extract/` that calls `json.loads`. It strips ```json fences, parses, iterates per-field policies, emits `llm_wobble` on every recovered field, constructs `into(**resolved)`, wraps in `Wobbled`. Existing `apply_policy` is retired as public surface (kept as `_apply_field` internal helper).

### Migrate the four canonical sites

| Site | Before | After |
|---|---|---|
| `extractor._split_answer_and_routing` | 78 LoC hand-rolled | ~13 LoC delegating to `parse_with_policy(into=RouterPayload, policies=_ROUTING_POLICIES)` |
| `extractor._split_answer_and_next_links` | hand-rolled | delegates with `_NEXT_LINKS_POLICIES` |
| `judge.parse_verdict` | already wobble-aware; reshape to use funnel | one call to `parse_with_policy` |
| `bench_judge._parse_clarity` + `_parse_next_links` | already wobble-aware; reshape | each one call |
| `fetcher_response._project_routing` | manual `llm_wobble` emit | accepts `Wobbled[RouterPayload]`, no parsing of its own |

### Type the seam

`Extractor.extract` returns `ExtractionResult` today. The internal helpers `_split_answer_*` return `tuple[str, T | None]`. After this change, the helpers return `tuple[str, Wobbled | None]`. `_project_routing` accepts `Wobbled`, not a bare `RouterPayload | None`. Downstream consumers of `RouterPayload` (`fetcher.py`) unwrap once at the seam.

### Backstop rule

Belongs to the `arch-fitness-functions-bootstrap` change, not this one — but referenced here so reviewers know the funnel is enforced:

```python
# tests/architecture/test_wobble_funnel.py (lands in the bootstrap change)
def test_only_wobble_calls_json_loads_in_llm_extract():
    """No json.loads call in packages/llm_extract/ outside wobble/."""
```

## Impact

**Code-shape changes**
- `packages/llm_extract/wobble.py` (130 LoC) → `wobble/` folder (~200 LoC across three files, including the new funnel)
- `packages/llm_extract/extractor.py` (-65 LoC net at the two `_split_*` sites)
- `packages/llm_extract/judge.py`, `bench_judge.py` — refactor to call the funnel; no net LoC change
- `fetcher_response.py::_project_routing` — accepts `Wobbled[RouterPayload]`; drops its own `llm_wobble` emit
- `packages/llm_extract/__init__.py` — re-exports new surface; `apply_policy` removed from public exports (breaking inside the package only)

**Wire / external contracts**
- **No wire changes.** `AskResponse` and `FetchResponse` are byte-stable. Only internal types shift.
- **`llm_wobble` event becomes universal.** Operators currently see wobble events from 2 sites; after this change, all 4. Existing dashboards key off the boundary label, which already differentiates.

**Tests**
- All existing wobble tests pass (existing public API preserved on the new surface).
- New tests assert `Wobbled` is only constructable via `parse_with_policy` (cooperative test — Python NewType is structural at runtime, so this is a smoke test, not a hard guarantee; the archon rule is the hard guarantee).
- Capability tests at `tests/capabilities/output_benchmark/` unaffected (envelope-level).

**Risk**
- LOW. The two non-conforming sites' current behaviour is silent recovery; the new behaviour is silent recovery *plus* an `llm_wobble` warning log. No functional change.
- ONE caveat: `_split_answer_and_routing` today returns `(text, None)` on malformed envelopes. After the change it returns the same — `parse_with_policy` raises `ParseError` on JSON decode failure, caller catches and substitutes `(text, None)`. Existing test cases (`tests/packages/llm_extract/test_extractor_router_parse.py`) confirm shape parity.

**Out of scope (deferred to other changes)**
- The `json.loads` ban rule itself — lands in `arch-fitness-functions-bootstrap`.
- Migrating wobble to a2kit (would require LARP — phantom-types + beartype). Future consideration only.
- Composite refactor of `AskResponse` (sub-objects PageClassification / NextSteps) — separate concern, not blocked by this change.
