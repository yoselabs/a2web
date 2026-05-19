# a2kit feedback — round 10 (v0.38 review)

From: a2web v0.7 on `a2kit v0.38`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Date: 2026-05-15
Context: read after rounds 7–9 (`A2KIT_FEEDBACK.md`, `A2KIT_FEEDBACK_v0.32-mcp.md`, `A2KIT_FEEDBACK_v0.33.md`) and `A2KIT_WISHES_DEFERRED.md`. The v0.32 → v0.38 cascade (DI rebuild, lifecycle consolidation, MCP `ctx`-binding fix, BaseSettings auto-resolve, lazy first-use, `Lazy[T]`) is **shipped, working, and the cleanest migration of all rounds.** 387 tests green on v0.38, zero residue per audit (only finding was one stale docstring in `events/__init__.py:3`).

This round is **friction inventory** — not bugs, not blockers. Recurring rough edges that every consumer reinvents. Ordered by how often they show up in a typical `App` composition.

---

## Friction A — Test-harness boilerplate every consumer reinvents

Three helpers in `tests/conftest.py` that should arguably live in a2kit:

### A1. `lazy_of(value)` — wrapping a fake for a `Lazy[T]` tool kwarg

```python
# conftest.py:34-45
def lazy_of(value: object) -> object:
    async def _thunk() -> object:
        return value
    return _thunk
```

`Lazy[T]` is `Callable[[], Awaitable[T]]`. Every test that injects a pre-built fake into a tool declaring `Lazy[T]` hand-rolls this. Five-line helper, but every consumer writes it.

**Ask:** ship `a2kit.testing.lazy(value)` (or `Lazy.of(value)` constructor). One-liner in the framework, deletes the helper from every consumer's conftest.

### A2. Autouse ambient-LDD fixture — required to call orchestrator functions directly

```python
# conftest.py:71-79
@pytest.fixture(autouse=True)
def _ambient_ldd():
    with ldd_state_for_call(
        ctx=null_context(),
        events_enabled=False,
        reports_enabled=False,
    ):
        yield
```

Any test that calls an orchestrator function directly (i.e. bypasses `TestClient.invoke`) hits `AmbientContextMissing` unless this autouse fixture is in place. The pattern is universal — every consumer with phase functions that emit LDD events writes the same fixture.

**Ask:** ship `a2kit.testing.ambient_for_tests` as a ready-made autouse fixture (or pytest plugin). Or — more invasive — make LDD primitives silent no-ops outside an active dispatch (with optional `A2KIT_LDD_STRICT=1` to restore current loud-raise behavior).

### A3. `make_default_state(...)` for direct-DI bypass

```python
# conftest.py:48-68
def make_default_state(settings: AppSettings | None = None) -> AppState:
    return build_state(
        settings=s,
        breakers=AsyncCircuitBreakerFactory(...),
        proxy_pool=ProxyPool(...),
        sqlite=SqliteResource(),
    )
```

This is consumer-domain, not a2kit's problem directly. **But** — the reason this helper exists is that there's no clean public way to say "give me the resolved DI singleton for T as if a tool had just been invoked." We use `a2kit.testing.peek(app, T)` for sync singleton inspection, but it doesn't run the dependency chain.

**Ask (smell, not bug):** `await a2kit.testing.resolve(app, T)` that runs the full async DI resolution chain and returns the resolved value, equivalent to what the dispatcher would inject into a tool kwarg. Would let `make_default_state` collapse to `state = await a2kit.testing.resolve(app, AppState)`.

---

## Friction B — `ctx` declaration ceremony (the every-router smell)

`src/a2web/routers.py:95-116`:

```python
async def fetch(
    self,
    *,
    url: ...,
    ...
    ctx: a2kit.ToolContext,   # required so dispatcher binds ambient state
) -> FetchResponse:
    del ctx  # tool body never uses it; phases emit via a2kit.ldd ambient
    ...
```

Every router declares `ctx: a2kit.ToolContext` purely to flip a flag in the dispatcher's wire layer, then `del ctx` because the tool body never touches it. The ceremony has no semantic meaning to the tool author — they just have to remember to declare it, or every LDD primitive downstream raises `AmbientContextMissing` (per OPERATIONAL_CONTRACTS Q8).

This is the cumulative friction round 7 wish 3 (sharper error message) was a partial fix for. The deeper question: **why does the tool body need to declare it at all?**

The framework already owns the dispatch. It already runs `ldd_state_for_call(...)`. The only thing the `ctx` param does today is signal "yes, also bind ctx on the ambient state object" — but if the tool body doesn't declare ctx, every downstream LDD primitive crashes anyway. The opt-out optimization (no ctx → no ambient bind) saves nothing in practice.

**Ask:** bind ambient ctx unconditionally for every framework-dispatched tool. Drop the `ctx: ToolContext` requirement from the tool signature. Tools that genuinely want ctx (e.g. `await ctx.report(...)` directly in the body) can still pull it from `a2kit.ldd.current_ctx()` or accept it as a kwarg — but the *default* should be: no ceremony, no `del ctx`.

If that's too invasive, fallback ask: a class-level `@a2kit.uses_ldd` marker on the Router that opts every tool in without each one declaring the param.

---

## Friction C — Canonical public surface lives 3 modules deep

```python
# routers.py:10
from a2kit.packages.di import Lazy

# CLAUDE.md prescribed pattern
from a2kit.packages.testing.client import client as make_client

# events/sinks.py:15
from a2kit.packages.ldd import LddEmission
```

`Lazy` is *the* most-touched DI primitive at the tool seam. It belongs at `a2kit.Lazy`, not `a2kit.packages.di.Lazy`. Same for `TestClient` and `LddEmission` — round 9 raised the `.call → .invoke` rename, but the deeper friction is that the canonical public surface is buried beneath `a2kit.packages.*`, which reads like internal scaffolding.

**Ask:** promote canonical types to top-level re-exports. The mental model should be:
- `a2kit.App`, `a2kit.Router`, `a2kit.ToolContext`, `a2kit.HealthResult` ✓ (already there)
- `a2kit.Lazy` — currently `a2kit.packages.di.Lazy`
- `a2kit.LddEmission` — currently `a2kit.packages.ldd.LddEmission`
- `a2kit.testing.client`, `a2kit.testing.peek`, `a2kit.testing.null_context` — currently mixed (`a2kit.testing` already exposes `null_context`, but `client` is at `a2kit.packages.testing.client`)

Promote, then document `a2kit.packages.*` as **private** — same convention as Python stdlib's `_thread` / `threading`.

---

## Friction D — `pydantic.Field` description ceremony

`src/a2web/routers.py:31-91` — five tool params, each:

```python
url: Annotated[
    str,
    pydantic.Field(
        description="Absolute http(s) URL to fetch.",
    ),
],
```

60-70% of `routers.py` is `Annotated[T, pydantic.Field(description="...")]` wrapping. `a2kit.Param` was retired in v0.31 — correctly, because owning a description primitive duplicates pydantic. But the verbosity has a real cost: tool author skims 130 lines of router to find which 5 are the actual tool logic.

**Ask (sugar, not primitive):** ship `a2kit.desc("…")` that expands to `pydantic.Field(description=…)`. Or `a2kit.param(description=…, default=…)` for the default+description combo. Doesn't replace `Annotated[]` — just shaves the import-and-wrap ceremony. Each param drops from 8-12 lines to 2-3.

This is the lowest-priority ask in this round. Worth bundling into a future polish release.

---

## Friction E — `AppState` is forced to split into "always-on" vs "lazy"

The v0.38 architecture has us push `BrowserPool` and `LlmExtractorResource` *off* `AppState` and onto the tool seam as `Lazy[T]` kwargs. The split is **correct for cold-start** — a fetch that doesn't need the browser shouldn't pay to construct the browser pool. But the consumer-side consequence is:

```
   tool kwargs                orchestrator                  phase fn
   ─────────────              ─────────────                ─────────
   state: AppState     ───►   fc.state           ───►     4 resources via fc.state
   browser: Lazy[T]    ───►   unwrap once        ───►     pass resolved value
   llm:     Lazy[T]    ───►   unwrap once        ───►     pass resolved value
```

Six total resources, but the tool signature carries two of them separately from state, and every phase function that needs them takes them as additional kwargs from the orchestrator (not reachable through `fc.state`). The architectural split is forced by the lazy-vs-eager distinction in the framework.

**Ask (open-ended, parked-candidate):** let `AppState`-like aggregates carry `Lazy[T]` fields, and have the framework respect them — resolve on first attribute access, register the entered resource on the lifecycle stack at that point. Then:

```python
@dataclass(slots=True)
class AppState:
    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    proxy_pool: ProxyPool
    sqlite: SqliteResource
    browser_pool: Lazy[BrowserPool]      # ← framework-aware
    llm_extractor: Lazy[LlmExtractorResource]
```

The tool signature collapses to `state: AppState, ctx: ToolContext`. Lazy is a field-level annotation, not a tool-signature concern. Phase functions get the lazy handles via `state.browser_pool` and unwrap at the call site.

Parked because: works as-is, the split is documentable, no current blocker. Worth scoping if/when other consumers report the same split.

---

## Friction F — Health-check probes private API

`src/a2web/server.py:111-122`:

```python
@app.health_check
async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
    try:
        await sqlite._ensure()   # ← underscore-prefixed internal method
    except Exception as exc:
        return a2kit.HealthResult.fail(f"sqlite open failed: {exc}")
    return a2kit.HealthResult.ok()
```

`_ensure()` is documented in a2web's CLAUDE.md as the internal lazy-call surface; the public CM protocol is `__aenter__`/`__aexit__`. The framework enters the resource on first resolution — so by the time `_check_sqlite` receives `sqlite: SqliteResource`, the resource *should* already be entered. But the explicit `await sqlite._ensure()` is there as belt-and-suspenders.

Two possible reads:
1. **The framework already does this** — kwarg resolution triggers `__aenter__`, so the explicit `_ensure()` is redundant. Then a2kit could document that "resolving a resource kwarg in `@app.health_check` is the probe."
2. **The framework doesn't enter for `@app.health_check`-resolved kwargs** — only for tool kwargs. Then a2web is right to call `_ensure()`, but pokes a private surface.

**Ask:** clarify and/or add `Resource.warm_up()` as the public probe primitive. Either way, `_ensure()` calls in consumer code should go away.

---

## Friction G — Recurring outstanding items (status carry-over)

| Round | Item | v0.38 status | Restated this round? |
|---|---|---|---|
| 7 | `app.singleton(..., teardown=fn)` | Superseded by v0.36 lazy CM ✓ | Closed |
| 7 | `Router.tools` decorator-time enforcement | Still open | Restated implicitly — see Friction B (related ceremony) |
| 7 | Sharper `AmbientContextMissing` for missing-ctx-param | Still open | Superseded by Friction B (deeper fix) |
| 9 | Per-class method-surface drift gate | Still open | Restated as Friction C (canonical surface) |
| 9 | `App(health_tool=True)` removal target | Still open | No fresh signal — defer |
| def | Streaming response API | Parked | No fresh signal |
| def | `@a2kit.read(timeout=...)` | Parked | No fresh signal |

---

## Top 3 if you only fix three

```
┌─────────────────────────────────────────────────────────────────┐
│  Priority    │ Friction │ Why this one                          │
├──────────────┼──────────┼───────────────────────────────────────┤
│  1  Highest  │   B      │ Touches every router, every consumer  │
│              │          │ `del ctx` smell is unfixable in       │
│              │          │ user code                             │
│              │          │                                       │
│  2  High     │   A      │ Three boilerplate helpers ×           │
│              │          │ every consumer. Pure framework win.   │
│              │          │                                       │
│  3  Medium   │   C      │ Public surface depth — `a2kit.Lazy`,  │
│              │          │ `a2kit.testing.client`. Promotes      │
│              │          │ canonical, deprecates `packages.*`    │
└─────────────────────────────────────────────────────────────────┘
```

D, E, F are polish — bundle into a future round when 2-3 more wishes accumulate.

---

## What we're NOT asking for

- Reverting any v0.36-v0.38 changes. The lazy-first-use rebuild + `Lazy[T]` + standalone DI is the right architecture.
- Faster releases. Cadence is fine.
- New API surface. Every friction above is "remove ceremony" or "promote existing surface."

---

## Migration status

a2web v0.7 on a2kit v0.38, openspec archive `2026-05-15-a2kit-v038-migration/`.

- 387 tests green
- Audit (this round) found exactly one stale docstring (`events/__init__.py:3`)
- Zero `a2kit.Param`, `idempotent=`, `lifespan=`, `app.singleton`, `@on_startup`, `atexit`, `tier_extras`, or other transition residue
- All resources expose `__aenter__`/`__aexit__` thin wrappers
- All heavy/conditional resources are `Lazy[T]` at the tool seam
- Router has `slug` + `tools: ClassVar[tuple[...]]`
- All event emission goes through `a2kit.ldd.event(TypedInstance(...))` with ambient ctx

Happy to draft any of the framework-side patches above with a concrete branch / smoke test if useful.

Thanks for the v0.36-v0.38 cascade — it's the migration we've been wanting for six rounds.

---

## Status — shipped in a2kit v0.39 (2026-05-16)

Frictions A1, A2, B, F shipped in v0.39 and are adopted by a2web in change `2026-05-16-a2kit-v039-migration` (archive). Specifically:

- **A1 — `a2kit.testing.lazy(value)`** — drop-in replacement for the `lazy_of(value)` helper a2web hand-rolled. Adopted.
- **A2 — `a2kit.testing.ambient_for_tests`** — pytest fixture; a2web re-exports under `pytest.fixture(autouse=True)` using the documented `__wrapped__` unwrap pattern. Adopted.
- **B — ambient ctx unconditional** — v0.39 MCP wrapper synthesizes `_a2kit_ctx` for tools that don't declare `ctx`; CLI mirrors. a2web dropped `ctx: a2kit.ToolContext` + `del ctx` from `WebRouter.fetch`. Adopted.
- **F — health probe `_ensure()` is obsolete** — kwarg resolution enters the resource; `OPERATIONAL_CONTRACTS Q-HealthChecks` pins the contract. a2web dropped `await sqlite._ensure()` from `_check_sqlite` and the surrounding try/except. Adopted.

**A3 — `a2kit.testing.resolve(app, T)`** — shipped, but a2web **did not adopt** for `make_default_state`. After review, `make_default_state` is the deliberate "AppState without an app" test seam — it constructs `AppState` synchronously for tests that call `fetch()` directly without composing an app. `resolve(app, T)` requires `async with app:` scope; it's the right tool for the *other* shape (tests inside an app scope), which a2web does not currently use. The friction filing was misdirected. Kept as-is.

**E — fold `Lazy[T]` resources into `AppState`** — v0.39 shipped `Lazy[T]` recognition in factory parameters (closes a real spec drift), enabling this pattern. a2web **retracted Friction E** during the v0.39 adoption pass — the architectural split (`AppState` for always-on data, separate `Lazy[T]` DI kwargs at the tool seam for orthogonal services like `BrowserPool` and `LlmExtractorResource`) is correct design, not friction. `AppState` is a data bundle; lifecycles, lazy resolution, and conditional resolution are service concerns. Funneling services through state would blur the seam, force every test to fake services it doesn't exercise, and hide which tool needs which resource. The capability exists in v0.39 if a future consumer wants it; a2web does not.

**ToolContext as Protocol** — verified no-op for a2web (zero `is fastmcp.Context` / `isinstance(..., ToolContext)` identity checks).

**C — canonical `a2kit.Lazy` / `a2kit.LddEmission`** — NOT shipped in v0.39. Stays deferred (see `A2KIT_WISHES_DEFERRED.md`). Partial win: `a2kit.testing.{lazy, ambient_for_tests, resolve, client}` IS the canonical surface now.

**D — `pydantic.Field` description sugar** — NOT shipped in v0.39. Stays deferred.

a2web on a2kit v0.39: 414 tests green, 89% coverage, both wire surfaces (MCP + CLI) verified.
