# a2kit feedback — round 4

From: a2web (now running on `a2kit v0.26+`, planning a simplification pass)
Audience: a2kit dev (AI agent or human — written self-contained either way)
Context: rounds 1-3 lived in `A2KIT_FEEDBACK.md` and were addressed across v0.24-v0.26. Lifecycle hooks, singletons, in-process test client, type-driven format routing, sink registration — all shipped and working. Thank you.

This round is **four ergonomic gaps + two soft notes**. None blocks anything. All surfaced while auditing a2web for simplification and asking "is this code load-bearing, or is it shim against a2kit's surface?" The items below are the latter.

The bar I'm using: every snippet of adapter code that exists *only* to bridge a2kit's API to typed Python is a tax that scales with the ecosystem. Worth fixing at the framework once instead of in every consumer.

---

## Gap 1 — Typed-emit half-shipped: `register(T)` works, but emit still wants kwargs

### What we have today

a2web defines typed phase-boundary events as dataclasses:

```python
# src/a2web/events/types.py
@dataclass(slots=True)
class TierStarted:
    t_ms: int
    step: str
    engine: str | None = None
    host: str | None = None
    proxy: str | None = None

@dataclass(slots=True)
class TierEnded:
    t_ms: int
    step: str
    engine: str | None
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)
```

Per the v0.26 README, we register them:

```python
# src/a2web/server.py
app.ldd.events.register(TierStarted)
app.ldd.events.register(TierEnded)
app.ldd.events.register(StageStarted)
app.ldd.events.register(StageEnded)
app.ldd.events.register(TierHeartbeat)
```

So far so good — the registry knows the types.

### The friction

The actual emit call still takes `name + **kwargs`, not the payload:

```python
# src/a2web/fetcher.py — required adapter shim
async def _emit(ctx: a2kit.ToolContext | None, event) -> None:
    if ctx is None:
        return
    await a2kit.ldd.event(ctx, event.__class__.__name__, **_event_payload(event))


def _event_payload(event) -> dict:
    """Flatten a dataclass event into kwargs for a2kit.ldd.event."""
    payload: dict[str, object] = {"t_ms": event.t_ms, "step": event.step}
    if isinstance(event, TierEnded | StageEnded):
        payload["verdict"] = event.verdict.value
        payload["dur_ms"] = event.dur_ms
        if getattr(event, "extra", None):
            payload["extra"] = event.extra
    if isinstance(event, TierStarted):
        if event.engine:
            payload["engine"] = event.engine
        if event.host:
            payload["host"] = event.host
        if event.proxy:
            payload["proxy"] = event.proxy
    if isinstance(event, TierEnded) and event.engine:
        payload["engine"] = event.engine
    return payload
```

That's ~25 lines of hand-rolled flattener that every consumer with typed events will rewrite. Worse, the `isinstance` branches will silently drop fields if we add new event types and forget to update the flattener. Untyped at the seam.

### What we'd like

The `register(T)` API hints at a typed-emit path. We'd like the emit call to honor it:

```python
# Proposed
await a2kit.ldd.event(ctx, TierStarted(t_ms=42, step="raw", host="example.com"))
```

Semantics:
- The payload dataclass is the source of truth. a2kit reads fields (via `dataclasses.asdict` or pydantic equivalent) and forwards them as the wire payload.
- `name` defaults to the class name; explicit `name=` override stays available for the kwargs form.
- The current `a2kit.ldd.event(ctx, "name", **kwargs)` form still works (backward compatible).
- Optional: validate against registered types at emit time. Unregistered payload → warning or hard error (your call).

### Impact on a2web

- `_emit` collapses to one line (`await a2kit.ldd.event(ctx, event)`).
- `_event_payload` (25 LOC) is deleted.
- New event types can't silently drop fields — the dataclass *is* the schema.
- Verdict enum serialization (`.value`) becomes a2kit's responsibility, consistent across consumers.

Cost to a2kit: ~30 LOC + tests. Cost to consumers if not shipped: every typed-event-using app writes the same flattener.

---

## Gap 2 — Lifecycle hook DI inconsistency (`on_startup` should inject like `health_check` does)

### What works (and is great)

```python
# src/a2web/server.py
@app.health_check
async def _check_sqlite(state: AppState) -> a2kit.HealthResult:
    if state.sqlite is None:
        return a2kit.HealthResult.fail("sqlite not opened")
    return a2kit.HealthResult.ok()
```

a2kit resolves `state: AppState` from the container and injects it. Clean.

### What doesn't

The startup/shutdown hooks take the bare `App` and force manual container resolution:

```python
@app.on_startup
async def _open_resources(_app: a2kit.App) -> None:
    container = _app.container()
    if container is None:
        msg = "container() must be initialized after singleton(...) is registered"
        raise RuntimeError(msg)
    state = await container.resolve(AppState, connection=None)
    state.sqlite = await open_sqlite_with_schema(state.settings)


@app.on_shutdown
async def _close_resources(_app: a2kit.App) -> None:
    container = _app.container()
    if container is None:
        msg = "container() must be initialized after singleton(...) is registered"
        raise RuntimeError(msg)
    state = await container.resolve(AppState, connection=None)
    if state.sqlite is not None:
        await state.sqlite.close()
        state.sqlite = None
    if state.browser_pool is not None:
        await state.browser_pool.close()
        state.browser_pool = None
```

Two distinct annoyances:
1. **The `container() is None` guard is dead defensive code.** By the time startup fires, the singleton has been registered at module load. The branch can't trigger. But the static type forces us to write it.
2. **`connection=None` is dead surface for connectionless apps.** a2web has no per-instance connections; the param exists only because the resolver was designed for connection-aware apps.

### What we'd like

Make lifecycle hooks DI-aware like `health_check`:

```python
# Proposed
@app.on_startup
async def _open_resources(state: AppState) -> None:
    state.sqlite = await open_sqlite_with_schema(state.settings)


@app.on_shutdown
async def _close_resources(state: AppState) -> None:
    if state.sqlite is not None:
        await state.sqlite.close()
    if state.browser_pool is not None:
        await state.browser_pool.close()
```

Semantics:
- a2kit inspects the hook signature; if it requests singleton-registered types, resolve and inject.
- The `App`-taking form stays available (backward compatible) for hooks that genuinely need `App` access.
- For connectionless apps, no `connection=` param appears in the signature.

### Impact on a2web

- 14 LOC of ceremony deleted (the two guards + two resolves).
- Two lifecycle hooks become 4 lines each instead of 10.
- The inconsistency between `@health_check` and `@on_startup` disappears — same DI model everywhere.

This is the smallest "make the framework feel coherent" fix in the list.

---

## Gap 3 — Async singleton factories (the cascading `Optional` problem)

### The pattern that bites us

`app.singleton(T, factory=...)` requires a synchronous factory. Three a2web resources need an event loop to construct:

1. **sqlite** (`aiosqlite.connect(...)` is async)
2. **browser pool** (Camoufox needs `await AsyncCamoufox().__aenter__()`)
3. **LLM extractor** (constructs an httpx-AsyncClient internally; non-fatal if sync, but stylistically wrong)

Because the factory is sync, these can't be constructed in `build_state()`. So `AppState` carries them as `Optional`, and we open them in startup hooks (sqlite) or lazily on first use (browser, llm):

```python
# src/a2web/state.py
@dataclass(slots=True)
class AppState:
    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    log_writer: LogWriter
    proxy_pool: ProxyPool
    sqlite: aiosqlite.Connection | None = None         # ← forced Optional
    browser_pool: BrowserPool | None = None            # ← forced Optional
    browser_lock: asyncio.Lock | None = None           # ← lock leaks into state
    llm_extractor: Extractor | None = None             # ← forced Optional
    llm_lock: asyncio.Lock | None = None               # ← lock leaks into state
    llm_unavailable_reason: str | None = None
```

The `Optional` then propagates: every callsite that touches `state.sqlite` has to handle `None`. The `browser_lock`/`llm_lock` fields exist *only* because we have to coordinate concurrent first-touches outside the factory.

We can mitigate at the consumer side (encapsulate lazy-init inside `BrowserPool.start()`), but the sqlite case can't — its construction is genuinely async and there's no natural "first dispatch" moment to defer to.

### What we'd like

Either:

**Option A — async factories:**
```python
# Proposed
app.singleton(AppState, factory=build_state_async)

async def build_state_async(settings: AppSettings) -> AppState:
    return AppState(
        settings=settings,
        sqlite=await aiosqlite.connect(...),
        browser_pool=BrowserPool(...),  # sync construct, idempotent .start() later
        ...
    )
```

Resolution kicks the factory on the event loop the first time the singleton is requested (which is during startup hook execution — already on the loop).

**Option B — lifecycle-aware factories:**
```python
# Proposed
@app.singleton(AppState)
async def build_state(settings: AppSettings) -> AsyncIterator[AppState]:
    state = AppState(...)
    state.sqlite = await aiosqlite.connect(...)
    yield state
    await state.sqlite.close()  # auto-runs at shutdown
```

This shape unifies "construct" and "close" into one place — sidesteps `@on_shutdown` for resource cleanup entirely. Inspired by FastAPI's lifespan / pytest fixtures. It's the more ambitious option but earns more in ergonomics.

### Impact on a2web

- 4 `Optional` fields on `AppState` become non-Optional.
- 2 `Lock` fields disappear (Locks live inside each resource).
- `unavailable_reason` becomes a typed `Result`-style return from `start()`, not a state field.
- Every callsite that handles `state.sqlite is None` simplifies.
- `state.py` shrinks from 136 LOC to ~60.

Option B additionally lets us delete the entire `@on_shutdown` hook (just the `sqlite.close()` + `browser_pool.close()` calls move to the factory's post-`yield` block).

---

## Gap 4 — `_app.container()` returning Optional, `connection=None` dead surface

This is the smaller sibling of Gap 2 — surfacing it separately because it'd remain even if you adopted the DI-aware hook signature.

### What we see

```python
container = _app.container()
if container is None:
    raise RuntimeError("container() must be initialized after singleton(...) is registered")
state = await container.resolve(AppState, connection=None)
```

- `container()` returns `Optional` — but realistically can it be None after registration? If yes, when and what should we do about it? If no, the Optional return type is forcing dead defensive code.
- `connection=` is required-keyword-with-`None`-OK. For apps that don't use a2kit's connection-aware DI at all, this is dead surface that every resolve call has to type.

### What we'd like

- If `container()` can truly be None, document when and provide a `container_or_raise()` helper. If it can't, narrow the return type to `Container`.
- For connectionless apps, allow `container.resolve(T)` without `connection=` (default to None internally, or make the param keyword-only-with-default).
- Even better: a `connection_aware=False` flag on `App` that statically removes the parameter from the container API.

Trivial change, removes a paper cut for every connectionless a2kit app.

---

## Soft note A — `Annotated[T, a2kit.Param(description=...)]` is verbose at the surface

Not a complaint, more a calibration check. a2web's `WebRouter.fetch` signature is 60 lines, of which ~80% is `Param(description=...)` prose:

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(
    self,
    *,
    url: Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")],
    include_links: Annotated[
        bool,
        a2kit.Param(description=(
            "Include the extracted `links` array in the response. Default "
            "False — links are a large share of payload bytes on aggregator "
            "pages (HN, PyPI, GitHub trending) and most tasks don't need them. "
            "Pass True for list-extraction tasks."
        )),
    ] = False,
    debug: Annotated[
        bool,
        a2kit.Param(description=(
            "Return the full `diagnostics` trace and per-tier rows. Default "
            "False — a one-line `diagnostics_summary` is always populated."
        )),
    ] = False,
    ...
) -> FetchResponse:
    """Fetch web content via an adaptive cascade with diagnostic trace.

    Tries site-specific handlers first ...
    """
```

The descriptions are good for MCP self-description (agents reading `list_tools` see exactly what each param does). But the function reads as 80% schema, 20% Python.

**Possible directions** (no strong preference, just options):

1. **Accept the verbosity** — it's the price of self-describing tools, agents need it. The wish here is just better docs on "this is intentional, here's how to structure long descriptions."
2. **Parse param descriptions from the docstring** — e.g., Google/NumPy-style `Args:` block. The function signature stays clean; descriptions live in one place.
3. **Allow shorter `Param("description text")` positional form** when description is the only field. Cosmetic.

If (2): need a convention. The risk is that docstrings and signatures drift, but agents are great at maintaining that consistency. The reward is signatures you can scan in 10 seconds.

Soft because the current form *works* — we just notice every new tool adds 30+ lines of `Param(description=...)` before the body starts.

---

## Soft note B — `ToolContext | None` propagation for testability

When a2web's orchestrator phases are unit-tested directly (bypassing `a2kit.testing.client(app)`), they receive `ctx=None`. So every phase function signature carries `ctx: a2kit.ToolContext | None`, and every emit-site does `if ctx is None: return`.

`a2kit.testing.client(app)` solves this for end-to-end tool tests — and we love it. But internal phase tests still want a no-ctx path.

### What we'd like

A `a2kit.ToolContext.null()` (or `a2kit.NULL_CTX` constant) — a no-op ToolContext shim that consumes events/reports silently. Then internal functions can take `ctx: a2kit.ToolContext` (non-Optional), tests construct the null one, and the `if ctx is None` guards vanish from production code.

Trivial change, ~10 LOC in a2kit, removes ~6 None-checks across a2web's phase functions.

(Alternative: just document "construct a `_NullToolContext` in your test helpers." We'll do that if you don't want to ship it.)

---

## What we're NOT asking for this round

- Per-tool timeout decorator kwarg — still on the wishlist (round 3 wish 1) but no escalation.
- Streaming response — still on the wishlist (round 3 wish 2).
- Anything connection-related — a2web has no connection concept.
- Auto-retry, built-in caching, built-in proxy — out of scope, app concern.

---

## Priority summary

| Gap | Severity | a2kit effort | Consumer savings if shipped |
|---|---|---|---|
| **1. Typed-emit honors `register(T)`** | medium | ~30 LOC | ~25 LOC per typed-event consumer; type safety |
| **2. Lifecycle hook DI like `health_check`** | medium-low | ~20 LOC | ~14 LOC + a coherence win |
| **3. Async singleton factories** | medium | ~50 LOC (Option A) / more (Option B) | 4 Optional fields + 2 Locks per resource-heavy app |
| **4. `container()` non-Optional + drop `connection=None`** | low | ~10 LOC | 1 dead-code guard per lifecycle hook |
| **A. Param description verbosity** | soft note | docs or feature | none required |
| **B. `ToolContext.null()` for tests** | soft note | ~10 LOC | nicer test ergonomics |

If you ship **1 + 2 + 4 + B** (the four small ones), a2web drops ~50 LOC of pure-adapter code and the framework feels noticeably more coherent. **3** is the bigger one — most impact per unit effort if Option B (lifespan-style factory) is on the table, but it's a larger surface change.

---

## Migration status / context

a2web is post-migration to a2kit v0.26+. The lifecycle + singleton + LDD sink registration triple from rounds 1-3 all landed and are working in production. This round's findings emerged from a follow-up simplification audit (see commit history around `v0.4-llm-module` and the in-progress engine cleanup) — they're the residual friction after the big wins shipped.

Happy to provide more concrete repros, run experimental APIs against a2web's test suite, or anything else useful.

Thanks again.
