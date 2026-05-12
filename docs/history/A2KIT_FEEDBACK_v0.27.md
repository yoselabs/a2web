# a2kit feedback — round 5

From: a2web (now running on `a2kit v0.27.2` + commit `3fffc3b` for `ldd.log`)
Audience: a2kit dev (AI agent or human — written self-contained either way)
Context: rounds 1-4 shipped across v0.24-v0.27.2. Lifecycle hooks, singletons, in-process test client, type-driven format routing, sink registration, typed-emit, Resource pattern, DI-aware lifecycle — all working. Thank you.

This round is **four ergonomic ceilings** noticed during a "radical simplification" sweep of a2web (commits `8fa524b` through `cf37742`, 2026-05-12). The packages migration deleted ~600 LOC of seam shims. The friction that remains is no longer "missing a feature" — it's "a2kit's surface forces a pattern we work around."

Same bar as round 4: every snippet of adapter code that exists *only* to bridge a2kit's API is a tax that scales with the ecosystem. Worth fixing once at the framework.

---

## Gap 1 — Resource pattern is great, but it's still framework-side scaffolding

### What we have today

a2kit v0.27 README documents the Resource pattern: sync `__init__`, internal `asyncio.Lock`, lazy `_ensure()`, idempotent `close()`. a2web adopted it for three resources:

```python
# src/a2web/packages/http_cache.py
class SqliteResource:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is None:
                self._conn = await open_sqlite_with_schema(self._db_path)
            return self._conn

    async def close(self) -> None:
        if self._conn is None:
            return
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
```

Same shape, three times: `SqliteResource`, `BrowserPool`, `LlmExtractorResource`. That's ~60 LOC of double-checked-locking + close-idempotency boilerplate before any business logic.

Callers either `await resource._ensure()` (and use the underlying object directly) or call resource-level shortcuts (`resource.get(url, profile_hash)`). The `_ensure()` ceremony is exposed in every consumer.

### The problem

The pattern is documented as "the canonical way to wrap async resources for sync DI." That admits it's a workaround. What we actually want:

```python
# Imaginary a2kit API
@app.async_resource
async def aiosqlite_connection(settings: AppSettings) -> aiosqlite.Connection:
    """Open at first-use, close at shutdown. a2kit manages the lock."""
    return await open_sqlite_with_schema(settings.cache_db_path)
```

Then phases inject the connection directly:

```python
async def _phase_cache_check(fc: FetchContext, *, conn: aiosqlite.Connection) -> None:
    fc.cached_row = await cache_get(conn, fc.url, fc.profile_hash)
```

No `_ensure()`, no wrapper class, no internal lock. a2kit owns the lifecycle. The Resource class collapses into the factory function.

### Why it matters

If a2kit ships first-class `@app.async_resource`, we delete:
- `SqliteResource` class entirely (replace with `open_sqlite_with_schema` as the factory)
- `LlmExtractorResource` class (replace with `build_extractor(settings, conn) -> Extractor | None` factory + None-handling at injection site)
- `BrowserPool._ensure()` (Camoufox launch happens in the factory)

That's ~80 LOC of boilerplate. The factory functions already exist — we just stop wrapping them in classes.

### Proposed API

```python
@app.async_resource(scope="app")  # one per App, opened on first use, closed at shutdown
async def aiosqlite_connection(settings: AppSettings) -> aiosqlite.Connection:
    ...

# Or for resources that may be None (LlmExtractorResource):
@app.async_resource(scope="app", optional=True)
async def llm_extractor(
    settings: AppSettings,
    conn: aiosqlite.Connection,
) -> Extractor | None:
    """Returns None on permanent unavailability — DI gives consumers Optional[T]."""
    ...
```

If `scope="request"` could lazily open per-tool-call (with shared connections pooled), that'd cover use cases the current `app.singleton(T, factory)` doesn't.

---

## Gap 2 — `ctx: ToolContext` threading is contagious

### What we have today

Every phase function in `src/a2web/fetcher.py` takes `ctx: a2kit.ToolContext` as a kwarg. Purpose: to call `a2kit.ldd.event(ctx, EventInstance(...))`.

```python
async def _phase_cache_check(fc: FetchContext, *, ctx: a2kit.ToolContext) -> None: ...
async def _phase_tier_loop(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None: ...
async def _phase_extract(fc: FetchContext, *, ctx: a2kit.ToolContext) -> None: ...
async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None: ...
async def _phase_cache_write(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None: ...
async def _escalate_browser(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None: ...
async def _dispatch_archive(url: str, *, state: AppState, ctx: a2kit.ToolContext, ...) -> _ArchiveOutcome: ...
async def _emit_tier_started(ctx: a2kit.ToolContext, ...) -> int: ...
async def _emit_tier_ended(ctx: a2kit.ToolContext, ...) -> int: ...
```

Nine functions. The ctx flows down the call chain purely to satisfy `a2kit.ldd.event(ctx, ...)`. Pure orchestration helpers like `_emit_tier_*` exist solely because passing `ctx` from the top everywhere is verbose.

Tests that invoke phases directly need `null_context()`:

```python
async def fetch(url: str, *, state: AppState, ctx: a2kit.ToolContext | None = None, ...):
    if ctx is None:
        from a2kit.testing import null_context
        ctx = null_context()
```

That entire `ctx is None` branch + `null_context()` import exists because tests can't easily get a real ctx.

### The problem

`ctx` is effectively a global of the current tool invocation. Python has `contextvars.ContextVar` precisely for this. If a2kit's tool dispatcher sets `_active_ctx: ContextVar[ToolContext]` on tool entry and clears it on exit, then `a2kit.ldd.event(...)` (no ctx arg) reads from the contextvar.

### Why it matters

If `ctx` becomes ambient:
- 9 function signatures lose a kwarg.
- `null_context()` is unneeded — `a2kit.ldd.event(...)` outside a tool call simply no-ops or raises.
- The `if ctx is None: ctx = null_context()` branch in `fetch()` deletes.
- Tests that don't care about events don't need to thread `ctx` through fixtures.

Net: ~30 LOC simpler in a2web, plus the cognitive load of "why does this pure helper take ctx" disappears.

### Proposed API

```python
# a2kit internals
_ctx_var: ContextVar[ToolContext] = ContextVar("a2kit_tool_ctx")

# at tool dispatch:
token = _ctx_var.set(ctx)
try:
    return await tool_fn(...)
finally:
    _ctx_var.reset(token)

# user code (current):
await a2kit.ldd.event(ctx, TierStarted(...))

# user code (proposed):
await a2kit.ldd.event(TierStarted(...))
```

`a2kit.ldd.event` reads `_ctx_var.get(None)`. When None (called outside a tool), it no-ops. When set, it dispatches to the tool's LDD channel.

Backward-compat path: keep `event(ctx, ...)` as overload, add `event(payload)` and treat `ctx` as ambient. Migrate consumers gradually.

---

## Gap 3 — No idiomatic test resource override

### What we have today

a2kit ships `a2kit.testing.peek(app)` for *reading* resource state in tests. There's no companion for *replacing* resources.

a2web tests work around this with `monkeypatch.setattr` on private attributes:

```python
# tests/test_fetcher_ask.py
state.llm_extractor._extractor = Extractor(...)  # ← private field injection
state.llm_extractor._unavailable_reason = None

# tests/test_browser_tier.py
class _StubPool:
    async def _ensure(self) -> None: ...
    def acquire(self, url: str) -> _StubPoolCtx: ...

state.browser_pool = _StubPool()  # type: ignore[assignment]
```

The type-ignore is a tell: we're routing around the type system to inject a fake.

### The problem

Tests that need stubs touch private state. That couples tests to implementation details that should move freely.

### Proposed API

```python
# at test construction:
with app.testing.override(SqliteResource, FakeSqlite()):
    result = await client.call("WebRouter.fetch", url=...)
    # FakeSqlite was injected for the duration; restored on exit
```

Or for fixture-style:

```python
@pytest.fixture
async def app_with_fake_sqlite(app):
    async with app.testing.override(SqliteResource, FakeSqlite()):
        yield app
```

a2kit knows the singleton/resource graph; it can swap one node for the test's duration. This is `unittest.mock.patch` semantics but typed and aware of the DI container.

### Why it matters

Tests stop depending on private attributes. Refactoring resources doesn't break unrelated tests. ~15 type-ignored monkeypatch sites across the test suite become idiomatic.

---

## Gap 4 — `Annotated[str, a2kit.Param(...)]` is verbose for the common case

### What we have today

```python
# src/a2web/routers.py
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(
    self,
    *,
    url: Annotated[str, a2kit.Param("Absolute http(s) URL to fetch.")],
    include_links: Annotated[
        bool,
        a2kit.Param(
            description=(
                "Include the extracted `links` array in the response. Default "
                "False — ..."
            ),
        ),
    ] = False,
    link_roles: Annotated[
        list[str] | None,
        a2kit.Param(
            description=(
                "When include_links=True, filter to these DOM roles. ..."
            ),
        ),
    ] = None,
    wrap_content: Annotated[
        bool,
        a2kit.Param(description=("...")),
    ] = True,
    # ... five more parameters
) -> FetchResponse:
```

Every parameter wraps its type in `Annotated[T, a2kit.Param(...)]`. The Param positional shorthand from round 4 helps (`Param("desc")` vs `Param(description="desc")`) but the `Annotated[T, ...]` wrapping is still 80 chars of visual noise around an 8-char type.

### The problem

Tool surface definitions become unreadable. The schema noise dominates the actual signature.

### Possible solutions

**Option A — pull from docstring:**

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(
    self,
    *,
    url: str,
    include_links: bool = False,
    link_roles: list[str] | None = None,
    wrap_content: bool = True,
    state: AppState,
    ctx: a2kit.ToolContext,
) -> FetchResponse:
    """Fetch web content via an adaptive cascade with diagnostic trace.

    Args:
        url: Absolute http(s) URL to fetch.
        include_links: Include the extracted `links` array. Default False.
        link_roles: When include_links=True, filter to these DOM roles.
            Choices: 'primary', 'nav', 'meta', 'footer'.
        wrap_content: Wrap content_md with HTML-comment markers.
    """
```

Standard Google/NumPy-style docstring sections; a2kit parses them at decoration time to populate Param descriptions. Zero `Annotated[...]` wrappers in the common case.

**Option B — `params=` kwarg on the decorator:**

```python
@a2kit.read(
    idempotent=True,
    open_world=True,
    title="Fetch Web Page",
    params={
        "url": "Absolute http(s) URL to fetch.",
        "include_links": "...",
        "link_roles": "...",
    },
)
async def fetch(self, *, url: str, include_links: bool = False, ...) -> FetchResponse: ...
```

Less elegant than A but easier to ship (no parser).

**Option C — leave alone, accept the noise.**

I'd vote A. The docstring already exists; reading it twice (once for humans, once for the MCP schema) is the natural fit.

### Why it matters

Tool definitions are the most-read code in any a2kit app — they're the API surface. Currently a 60-LOC method signature is 80% schema, 20% behavior. Readability matters.

---

## Soft note — exported symbol locations

`LddSink` (the Protocol that `app.ldd.add_sink(sink)` accepts) lives at `a2kit.ldd.LddSink`. Mostly fine, but consumers writing custom sinks have to know that import path. Re-exporting it at top-level `a2kit.LddSink` would match the convention used for `App`, `Router`, `Param`, `ToolContext`.

Same for `LddEmission` (the payload type passed to sinks).

Trivial — just adding two names to `a2kit/__init__.py`.

---

## What we'd delete after each gap is closed

| Gap | LOC removed in a2web |
|---|---|
| 1 (async Resources) | ~80 (three Resource classes collapse) |
| 2 (ambient ctx) | ~30 (ctx kwargs across phases + null_context branch) |
| 3 (test override) | ~15 (monkeypatch.setattr lines + type-ignores) |
| 4 (Param verbosity) | ~50 (Annotated wrappers in routers.py) |
| **Total** | **~175 LOC** |

Plus the cognitive load: future a2web contributors stop wondering "why does this pure phase function take ctx" or "why does my test poke at `_extractor` directly."

---

## Migration status / context

a2web post-v0.5 release (2026-05-12) finished a radical simplification:
- ~580 LOC deleted across the seam-shim layer
- 7 in-tree microsofware packages with a load-bearing invariant test
- Fetcher orchestrator decomposed; isinstance ladder gone via unified Tier signature
- Link role classification + untrusted-content envelope shipped as additive features

The four gaps above are the residual friction after the architectural wins. None blocks anything; all would compound nicely.

Happy to provide more concrete repros, run experimental APIs against a2web's 374-test suite, or anything else useful.

Thanks again.
