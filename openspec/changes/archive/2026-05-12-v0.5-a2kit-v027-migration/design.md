# Design — a2kit v0.27.2 migration

## The Resource pattern, applied to a2web

a2kit's v0.27 README §"Resource pattern (lazy-init)" specifies the canonical shape. Each long-lived async resource is a class:

- Sync `__init__` (no I/O).
- `_handle: SomeType | None` — internal, lazy-opened.
- `_lock: asyncio.Lock` — internal, created in `__init__`, lives forever.
- `async def _ensure(self) -> Handle` — double-checked-lock + open under lock.
- Async business methods that `await self._ensure()` internally.
- `async def close(self)` — idempotent.

AppState fields are non-Optional. Locks never leak to state. Compare today's `state.py` (136 LOC, 4 Optional resource fields, 2 standalone locks, 2 `ensure_*` free functions) to the target (~40 LOC, all non-Optional).

## Three resource classes

### `SqliteResource`

Wraps `aiosqlite.Connection` + schema bootstrap. Today's `open_sqlite_with_schema(settings)` becomes the body of `_ensure()`.

```
SqliteResource(settings)
  ├─ __init__(settings)              # sync, no I/O
  ├─ _conn: aiosqlite.Connection | None = None
  ├─ _lock: asyncio.Lock
  ├─ async _ensure() -> Connection   # double-checked + opens + applies schema
  ├─ async get(url, profile_hash) -> CacheRow | None
  ├─ async put(...)                  # current cache_put signature
  └─ async close()
```

This collapses the current free-function API in `cache/sqlite_cache.py` (`cache_get(conn, ...)`, `cache_put(conn, ...)`, `open_sqlite_with_schema(...)`) into methods on a single class. Callers go from `await cache_get(state.sqlite, url, hash)` to `await state.sqlite.get(url, hash)` — the `conn` argument disappears because it's `self`.

**Decision point during implementation:** keep the free functions in `cache/sqlite_cache.py` as thin wrappers around the class for backwards compatibility, or migrate all call sites to the methods in this same PR. Recommendation: migrate in this PR. Call sites are bounded (orchestrator phases + one place in fetcher). Tests are integration-level (real sqlite, just changes the dispatch shape). Cleaner diff than carrying a wrapper layer.

### `BrowserPool` (existing class, adopt pattern)

Today's `BrowserPool` is already close to the pattern — it has `start()`, `close()`, internal `_lock`. Changes needed:

- Rename `start()` to `_ensure()` for pattern conformance (or keep `start()` as a public alias).
- Make `_ensure()` idempotent under the lock with double-check (current `start()` returns early if `_browser is not None` but not under lock — concurrent first calls race).
- Move `state.browser_lock` into the class (delete from `AppState`).
- `acquire(url)` already calls into the pool; it just needs to call `_ensure()` first instead of relying on `ensure_browser_pool(state)` from state.py.
- `ImportError` on Camoufox missing — surfaced from `_ensure()`. `BrowserTier.fetch()` catches it and translates to operator hint (same as today).

`state.browser_pool: BrowserPool` becomes non-Optional. Construct in `build_state()` (sync); first `_ensure()` call inside `BrowserTier.fetch()` lazy-opens Firefox.

### `LlmExtractorResource`

Wraps today's `state.llm_extractor: Extractor | None` + `state.llm_lock` + `state.llm_unavailable_reason`. The "unavailable" tracking needs to survive — it's not a transient failure; we don't retry construction on every fetch.

```
LlmExtractorResource(settings)
  ├─ __init__(settings)
  ├─ _extractor: Extractor | None = None
  ├─ _unavailable_reason: str | None = None
  ├─ _lock: asyncio.Lock
  ├─ async _ensure() -> Extractor | None  # may return None on permanent unavail
  ├─ async extract(content_md, ask, ...) -> ExtractionResult | None
  ├─ unavailable_reason: str | None       # property, for operator-hint surfacing
  └─ async close()  # no-op today; symmetric
```

The `_ensure()` returns `None` (not raises) when the LLM is permanently unavailable (missing extra, missing API key). That distinguishes "config gap" from "transient SDK error." Callers check the return; on `None`, populate `OperatorHint` and skip.

### Note on `LogWriter` and `ProxyPool`

These are already non-Optional on `AppState` and construct synchronously. No Resource-pattern conversion needed.

## Lifecycle hooks — the new shape

```
@app.on_startup
async def _open_resources(state: AppState) -> None:
    """Fail-fast warm-up — surface config errors at startup, not first request."""
    await state.sqlite._ensure()
    # Skip browser + llm warm-up: optional deps, lazy on real first use.

@app.on_shutdown
async def _close_resources(state: AppState) -> None:
    """Close every Resource. Each `close()` is idempotent."""
    await state.sqlite.close()
    await state.browser_pool.close()
    await state.llm_extractor.close()
```

DI auto-resolves `state: AppState`. No `_app: a2kit.App`. No `container.resolve(...)`. No None-guards.

## Typed-emit migration

Today's `_emit` adapter:

```
await _emit(ctx, TierStarted(t_ms=42, step="raw", host="example.com"))
```

Replaced with direct typed-emit:

```
if ctx is not None:                                   # only because today's ctx can be None
    await a2kit.ldd.event(ctx, TierStarted(...))
```

After this migration removes `ctx: ToolContext | None`, the None-check disappears:

```
await a2kit.ldd.event(ctx, TierStarted(t_ms=42, step="raw", host="example.com"))
```

a2kit 0.26.1's typed-emit:
- Names the event from `type(event).__name__` (override with `name=` kwarg if needed).
- Flattens via `dataclasses.asdict` (works for our `@dataclass(slots=True)` event types).
- Coerces `Enum` field values via `.value` automatically. Our `Verdict` (StrEnum) serializes correctly.

`_event_payload` is deleted entirely — it was paying for what a2kit now does in one line.

## `ToolContext | None` → `ToolContext` everywhere

Every phase function signature changes:

```
async def _phase_tier_loop(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None) -> None:
                                                                    ↓
async def _phase_tier_loop(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None:
```

Every internal-test that constructs phase calls directly:

```
await _phase_tier_loop(fc, state=state, ctx=None)
                                            ↓
from a2kit.testing import null_context
await _phase_tier_loop(fc, state=state, ctx=null_context())
```

`null_context()` is a no-op shim — `event`, `report`, `log`, every wire method is a silent drain. Production code stays unaware.

## What stays the same

- `WebRouter.fetch` signature in `routers.py` — already takes `state: AppState, ctx: a2kit.ToolContext` via DI. No change needed at the router boundary.
- a2kit's `add_router`, `singleton`, decorators — surface unchanged.
- `app.ldd.events.register(...)` calls in `server.py` — still required for the typed-emit path to know the registered types. (a2kit could in theory infer from first emit, but explicit registration is part of the contract.)
- `app.ldd.add_sink(otel_sink)` — unchanged. OTel sink's collapse is a separate decision (thread 3) that depends on whether we keep typed events or move to inline spans. Not in this PR.

## Open questions to resolve during implementation

1. **Free functions in `cache/sqlite_cache.py` — delete or keep as wrappers?** Recommendation: delete. Migrate call sites to methods on `SqliteResource`. Cleaner. ~10 call sites total.
2. **Should `BrowserPool` rename `start()` → `_ensure()` or keep both?** Recommendation: rename. The leading underscore signals "internal, called by business methods." Public surface is `acquire()` / `close()`.
3. **Where does `LlmExtractorResource` live?** Recommendation: `src/a2web/llm/resource.py`. Keeps the LLM module self-contained. AppState imports it from there.
4. **Does the existing `bootstrap_state_for_test` function (CLAUDE.md mentions it's "gone" — verify) need any test-side adapter?** Verify during task list execution.

## Validation plan

After each commit:

1. `make lint` — ruff + ty pass.
2. `make test` — full pytest suite, coverage ≥85%.
3. Sanity manual: `uv run a2web web fetch --url=https://news.ycombinator.com` returns valid response.

After full migration:

1. Grep for absence of removed symbols: `_emit`, `_event_payload`, `ensure_browser_pool`, `ensure_llm_extractor`, `bootstrap_state_for_test`, `state.browser_lock`, `state.llm_lock`, `state.llm_unavailable_reason`.
2. Grep for absence of removed patterns: `ctx: a2kit.ToolContext | None`, `if ctx is None: return`, `container.resolve(..., connection=None)`, `_app: a2kit.App`.
3. Run E2E: `make dev`, hit the MCP `fetch` tool from a test agent, confirm typed events arrive on the wire.
