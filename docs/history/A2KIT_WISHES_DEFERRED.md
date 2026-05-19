# a2kit — deferred wishes (post-v0.29 migration)

Status: parked, not abandoned. None of these block a2web. They're recorded here so the next a2kit feedback round (round 7+) has a starting point and nothing falls between the cracks.

Last updated: 2026-05-13, after a2kit v0.28.0 → v0.29.1 shipped every gap from rounds 5 + 6.

---

## 1. Streaming response API (Q6 — first raised round 3)

### Context

`FetchResponse.content_md` can be 100KB+ for big articles. Today the calling agent waits for the entire body before any of it is visible. MCP supports chunked / streaming responses for this exact case.

### Two API shapes a2web would accept

```python
# (a) Yield from the tool body — async iterator
@a2kit.read(streaming=True)
async def fetch(*, url: str) -> AsyncIterator[FetchChunk]:
    async for chunk in fetcher.stream_fetch(url):
        yield chunk

# (b) Explicit chunk emit via ctx, terminal return for final shape
@a2kit.read(streaming=True)
async def fetch(*, url: str) -> FetchResponse:
    async for chunk in fetcher.stream_fetch(url):
        await ctx.chunk(chunk.markdown)
    return final_response
```

(a) composes better with type-driven format routing; (b) mirrors how `event` / `report` already work. Either is fine.

### Why parked

No current downstream caller has surfaced "I need streaming." Synchronous `FetchResponse` works. Reopens if a Claude Code MCP consumer reports latency complaints on long articles or if we add a "fetch + extract" tool that benefits from incremental output.

---

## 2. `@a2kit.read(timeout="60s")` decorator kwarg (round 3, wish 1)

### Context

`OPERATIONAL_CONTRACTS` Q2 documents the current contract: no built-in timeout, use `anyio.fail_after(seconds)` inside the tool body. Reasonable, but every network-facing tool wants this — wrapping each tool body in `async with anyio.fail_after(...):` is repetitive.

### Proposed surface

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page", timeout="60s")
async def fetch(*, url: str) -> FetchResponse:
    ...
```

Semantics:
- `timeout=None` (default) → current behavior, tool handles its own budgets
- `timeout="60s"` or `timeout=60.0` → dispatcher wraps body in `anyio.fail_after(60)`; `TimeoutError` bubbles per Q1/Q5 conventions
- Configured timeout surfaces in tool description / annotations so agents can decide retry policy

### Why parked

`anyio.fail_after` is one line in the tool body. Ergonomic, not load-bearing. Worth bundling into a future "decorator polish" round once 2-3 wishes accumulate.

---

## 3. Watch list — a2kit-internal openspec changes

The v0.28.0 CHANGELOG mentions two openspec changes that captured Tier 2/3/4 of the Context-shape divergence repair as follow-ups:

- `align-context-method-signatures`
- `rebuild-test-client-on-real-context`

These are a2kit-internal. Worth tracking — if they ship, we should audit a2web for any test-side reliance on the old TestClient shape (probably nothing, but worth a 10-minute pass).

---

## 4. `app.singleton(T, factory, teardown=fn)` — singleton-owned cleanup (round 7 candidate)

### Context

Surfaced during the v0.32 lifespan rewrite. With `@app.on_shutdown` removed, every consumer with async resources hand-rolls cleanup in the lifespan body's `finally`:

```python
@asynccontextmanager
async def lifespan(app):
    state = app.container().resolve(AppState)
    await state.sqlite._ensure()
    try:
        yield
    finally:
        for closer in (state.llm_extractor.close, state.browser_pool.close, state.sqlite.close):
            try:
                await closer()
            except Exception:
                pass
```

Three resources, three lines. Scales linearly with resource count, and every consumer reinvents the error-isolation wrapping.

### Proposal

```python
app.singleton(SqliteResource, factory=build_sqlite, teardown=lambda r: r.close())
app.singleton(BrowserPool, factory=build_pool, teardown=lambda p: p.close())
app.singleton(LlmExtractorResource, factory=build_llm, teardown=lambda x: x.close())
```

a2kit calls `teardown` on each resolved singleton at lifespan exit, in reverse-of-registration order, with each call error-isolated and logged via `a2kit.ldd.error` on failure. Lifespan body just yields (or runs business logic that doesn't touch resources).

### Why parked

`finally`-body explicit cleanup works. This is ergonomic, not blocking. Worth bundling with other "decorator polish" wishes whenever a round 7 lands.

---

## 5. Decorator-time enforcement of `tools` tuple completeness (round 7 candidate)

### Context

Surfaced during the v0.32 Router contract migration. v0.31's CHANGELOG notes:

> a decorated-but-unlisted method silently does NOT register (a follow-up lint rule will flag this drift statically)

The lint rule is "follow-up" — not yet shipped. Without it, adding a `@a2kit.read`-decorated method to a Router and forgetting to add it to the `tools` tuple silently produces a tool that's invisible on every transport. No error, no warning.

### Proposal

Either:
- Ship the planned static lint rule (preferred — catches at lint time, no runtime cost)
- OR raise at `Router.__init__` if any class-level callable has `_a2kit` meta but isn't in `tools`

### Why parked

a2web has only one router with one tool. Easy to keep mentally synced. Worth raising if/when we add a second tool.

---

## 6. `_LDD_STATE` / `_require_ambient_state` should accept `ctx=None` for tools that opt out of LDD

### Context

Surfaced during the v0.32 migration. A tool that doesn't declare `ctx: a2kit.ToolContext` cannot call `a2kit.ldd.event(...)` — `ldd_state_for_call` is invoked with `ctx=None`, and `event()` then crashes when it tries `ctx._emit(...)` because None has no `_emit`. This is documented in OPERATIONAL_CONTRACTS Q8 ("a no-ctx tool that calls `await a2kit.ldd.event(...)` raises identically on every dispatcher").

The current behavior (raise `AmbientContextMissing`) is reasonable but the error message could be sharper — "you forgot to declare `ctx: ToolContext` on this tool" is more actionable than "called outside an active tool dispatch" (which the user IS inside, just without a ctx-bound dispatch).

### Proposal

Refine the `AmbientContextMissing` message when `_LDD_STATE.ctx is None` (vs no state at all) to say: "tool body called LDD primitive but did not declare `ctx: a2kit.ToolContext` parameter — add it to the signature, or remove the LDD call." Two distinct error paths, each pointing at the actual fix.

### Why parked

The current message + OPERATIONAL_CONTRACTS Q8 is enough to debug. Pure DX polish.

---

## 7. Canonical-surface promotion (`a2kit.Lazy`, `a2kit.LddEmission`) — round-10 Friction C

### Context

After v0.39, the most-touched DI primitive at the tool seam still lives at `a2kit.packages.di.Lazy`. Similarly `a2kit.packages.ldd.LddEmission` for sink authors. The mental model should be:

- `a2kit.App`, `a2kit.Router`, `a2kit.ToolContext`, `a2kit.HealthResult` ✓ (already top-level)
- `a2kit.Lazy` — currently `a2kit.packages.di.Lazy`
- `a2kit.LddEmission` — currently `a2kit.packages.ldd.LddEmission`
- `a2kit.testing.{client, peek, lazy, ambient_for_tests, resolve, null_context}` — ✓ (now canonical)

### Ask

Promote `Lazy` and `LddEmission` to top-level re-exports. Document `a2kit.packages.*` as private (stdlib `_thread` / `threading` convention).

### Why parked

`from a2kit.packages.di import Lazy` works. Cosmetic / discoverability fix, not blocking. Worth bundling into a future polish round.

---

## 8. `pydantic.Field` description sugar (`a2kit.desc`) — round-10 Friction D

### Context

a2web `routers.py` is 60-70% `Annotated[T, pydantic.Field(description="...")]` ceremony. `a2kit.Param` was correctly retired (duplicated pydantic), but the verbosity has a real readability cost: each tool param spans 8-12 lines.

### Proposed sugar

```python
url: Annotated[str, a2kit.desc("Absolute http(s) URL to fetch.")]
```

…expands to `pydantic.Field(description=…)`. Or `a2kit.param(description=…, default=…)` for the description+default combo.

### Why parked

Cosmetic. Doesn't replace `Annotated[]` — just shaves the wrap. Lowest-priority polish item.

---

## How to retire an entry

When one of these ships in a2kit or stops mattering for a2web:

1. Move the entry to `docs/history/A2KIT_FEEDBACK_v<version>.md` with a one-line "shipped / dropped / superseded by X" note.
2. Delete the entry from this file.

Keeps this file lean and current.
