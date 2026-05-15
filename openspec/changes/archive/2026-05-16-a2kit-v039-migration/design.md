# Design — a2kit v0.39 migration

## Scope (after round-10 self-correction)

**Mechanical surface migration, not architectural restructuring.** The original draft proposed folding `Lazy[BrowserPool]` + `Lazy[LlmExtractorResource]` into `AppState`. That was wrong:

- `AppState` is a **data bundle**, not a service locator. Mixing always-on resources with lazy services blurs the seam.
- Tools declare exactly the services they use as Lazy DI kwargs — that's the contract.
- Tests that construct `AppState` directly shouldn't have to fake services they don't exercise.

v0.39's `Lazy[T]`-in-factory-params shipping is a real spec-drift fix. It's just not relevant to a2web. The Lazy-at-the-tool-seam pattern stays as the idiomatic shape.

## Architecture — unchanged

```
 app.provide(SqliteResource)            ← always-on
 app.provide(build_browser_pool)        ← service (heavy, conditional)
 app.provide(build_llm_extractor)       ← service (heavy, conditional)
 app.provide(build_state)               ← bundles the always-on four
 
 ┌──────────────────────┐
 │ AppState             │   data bundle
 │   settings           │   (no services here)
 │   breakers           │
 │   proxy_pool         │
 │   sqlite             │
 └──────────────────────┘
 
 fetch(*, url, ..., state: AppState,
       browser_pool: Lazy[BrowserPool],     ← service kwargs
       llm_extractor: Lazy[LlmExtractorResource])  ← tool contract is explicit
```

This is the v0.38 shape. The migration touches the *ceremony* around this shape (ctx declaration, conftest helpers, health probe internals), not the shape itself.

## Decisions

### D1 — Retract round-10 Friction E

`AppState` does NOT absorb `Lazy[BrowserPool]` / `Lazy[LlmExtractorResource]`. Update `A2KIT_FEEDBACK_v0.38.md` (round 10) to mark Friction E as **retracted by a2web — split is correct design**.

### D2 — Drop `ctx: a2kit.ToolContext` from `WebRouter.fetch`

v0.39 changelog: *"ambient `ctx` is non-None inside any framework dispatch"* and *"consumers can drop `ctx: a2kit.ToolContext` parameters from tools that didn't actually use ctx in the body."* `WebRouter.fetch` doesn't use ctx in the body — it `del ctx`s it. Drop both the param and the `del`.

A future tool that genuinely uses ctx in its body re-adds the param. The Protocol shape (v0.39) means the annotation satisfies both MCP and CLI transports structurally.

### D3 — Health check body shape

After dropping `_ensure()`:

```python
@app.health_check
async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
    """Framework enters sqlite via __aenter__ on kwarg resolution
    (OPERATIONAL_CONTRACTS Q-HealthChecks)."""
    _ = sqlite
    return a2kit.HealthResult.ok()
```

The `_ = sqlite` line is kept for grep-ability and to document "this is the readiness probe" — explicit assertion that we received the resource. Tasks Step 2 confirms whether the health framework wraps DI-construction failures; if it does, the try/except is redundant. If not, keep the try/except as belt-and-suspenders.

### D4 — Keep `make_default_state` as the deliberate test seam

`a2kit.testing.resolve(app, T)` requires `async with app:` scope. Many a2web tests construct `AppState` synchronously and call `fetch()` directly without composing an app — that's the deliberate test seam.

`make_default_state` is NOT the "boilerplate every consumer reinvents" that round-10 Friction A3 called out. It's the deliberate "AppState without an app" helper. Keep it.

`resolve(app, T)` is for the *other* shape — tests that do compose an app. We don't currently have many of those; if/when we add them, they'll use `resolve` directly.

### D5 — `ambient_for_tests` adoption pattern

Two plausible shapes for `a2kit.testing.ambient_for_tests`:

```python
# (a) pytest fixture — re-export under our own autouse=True wrapper
from a2kit.testing import ambient_for_tests as _ambient_inner
@pytest.fixture(autouse=True)
def _ambient_ldd(_ambient_inner):
    yield

# (b) context manager — wrap in our own autouse fixture
from a2kit.testing import ambient_for_tests as _ambient_cm
@pytest.fixture(autouse=True)
def _ambient_ldd():
    with _ambient_cm():
        yield
```

Tasks Step 0 confirms the shape by reading `a2kit.testing` module surface. Adapt the conftest based on what it is.

### D6 — `ToolContext` Protocol — verification only

v0.39 changelog: `a2kit.ToolContext` is now a `@runtime_checkable typing.Protocol`. `a2kit.ToolContext is fastmcp.Context` is now `False`. Grep a2web for `is fastmcp.Context` / `isinstance(..., ToolContext)` — expected zero hits. Then no code change.

### D7 — Round-10 retire

Add a status footer to `docs/history/A2KIT_FEEDBACK_v0.38.md`:

```
## Status — shipped in a2kit v0.39 (2026-05-16)

Frictions A1, A2, B, F shipped in v0.39 and are adopted by a2web in
change `a2kit-v039-migration`.

Friction A3 (`make_default_state` collapse via `a2kit.testing.resolve`)
was filed but rejected during adoption — the helper is a deliberate test
seam for "AppState without an app" composition. `resolve(app, T)` is for
the orthogonal "test inside an app scope" use case.

Friction E (fold Lazy resources into AppState) was filed but **retracted
by a2web** — the architectural split (`AppState` for data, separate Lazy
DI kwargs for services) is correct design. v0.39's `Lazy[T]`-in-factory
support closes a real spec drift, but a2web doesn't change.

Frictions C (canonical surface promotion) and D (Field description sugar)
remain deferred — see A2KIT_WISHES_DEFERRED.md.
```

## Migration order recap

| Step | What | Why this order |
|---|---|---|
| 0 | Pin bump + surface verification | Confirm v0.39 API before depending on it |
| 1 | Drop `ctx` from `WebRouter.fetch` + `del ctx` | Smallest mechanical change; loud failure if v0.39 not active |
| 2 | Drop `_ensure()` from `_check_sqlite` | Independent of step 1 |
| 3 | `conftest.py` helpers swap (`lazy_of` → `a2kit.testing.lazy`; ambient fixture) | Test-side; can be done in parallel with 1–2 |
| 4 | Stale docstring + grep audits | Final cleanup |
| 5 | CLAUDE.md + history docs | Documents the new idiom |
| 6 | `make check` end-to-end + MCP / CLI smokes | Final gate |

## What we're explicitly NOT changing

- `AppState` shape — stays narrow (4 fields).
- `build_state` signature — stays at 4 deps.
- `WebRouter.fetch` Lazy kwargs (`browser_pool`, `llm_extractor`) — stay.
- `fetcher.py` phase decomposition — unchanged.
- `make_default_state` helper — stays.
- Tier registry, handlers, packages, events, sinks — unchanged.
- Wire surface (tool name, response envelope, event payloads) — unchanged.
