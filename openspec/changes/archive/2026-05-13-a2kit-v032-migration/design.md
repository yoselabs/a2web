# Design — a2kit v0.32 migration

Five decisions need explicit framing before mechanical work starts. Everything else is grep-and-replace driven by `tasks.md`.

---

## Decision 1 — async-singleton shape per resource (unchanged from v0.29 plan)

a2kit v0.29.0's `app.singleton(T, async_factory)` pattern is preserved through v0.32. Decisions hold from the previous design with one verification flag:

### `aiosqlite.Connection` — collapse the wrapper
`SqliteResource` exists purely for lazy-open lifecycle. Collapse to direct `aiosqlite.Connection` registration via `app.singleton(aiosqlite.Connection, factory=open_sqlite_with_schema)`. Phases inject the connection.

### `BrowserPool` — keep the wrapper class
Owns acquire / per-host caps / eviction — domain logic. Register the class itself; the launch happens in the factory:
```python
async def build_browser_pool(settings: AppSettings) -> BrowserPool:
    pool = BrowserPool(settings=settings)
    await pool._launch()
    return pool

app.singleton(BrowserPool, factory=build_browser_pool)
```

### `Extractor | None` — collapse with verification gate
Replace `LlmExtractorResource` with `build_llm_extractor(settings, sqlite) -> Extractor | None`. Verification needed in **task 0a**: does `app.singleton(Extractor | None, ...)` accept a Union as the key, or do we register a `LlmExtractorHandle` dataclass? The API call goes through `register_singleton(type_: type, factory)` per `src/a2kit/packages/di/container.py:176`. Python `type` parameter doesn't strictly accept `Union` — likely fails. **Default plan: ship a `LlmExtractorHandle` dataclass.** Override during 0a if Union keys turn out to work.

```python
@dataclass(slots=True)
class LlmExtractorHandle:
    extractor: Extractor | None
    unavailable_reason: str | None  # populated when extractor is None
```

LOC neutral compared to the wrapper class collapse — but type-clean.

---

## Decision 2 — Lifespan over `@on_startup`/`@on_shutdown` (NEW for v0.31+)

This is the biggest architectural change in this migration. v0.31 deletes both lifecycle decorators and replaces them with a single `lifespan=` async-context-manager kwarg on `App(...)`. There is no shim and no compatibility path.

### Verified API surface (from a2kit v0.32 source)

- `App(name, ..., lifespan=lifespan)` — single positional arg `app: a2kit.App`. Framework does NOT introspect signature beyond shape.
- `await app.warm_async_singletons()` — explicit replacement for the implicit `@on_startup` warm of async-factory singletons. Iterates registry, awaits each async-factory entry through the container; idempotent.
- `app.lifespan_cm()` — composed lifespan as async context manager (user lifespan + every Router's lifespan via `a2kit.lifespan.compose`).
- TestClient `__aenter__` enters `app.lifespan_cm()`; `__aexit__` exits it.
- FastMCP integration: `build_mcp_server(app)` wraps `app.lifespan_cm()` for FastMCP's `lifespan=` slot.

### Resource cleanup — explicit, no teardown kwarg

`app.singleton(T, factory)` does NOT accept a `teardown=` or `close=` kwarg in v0.32 (verified via source — `register_singleton(type_, factory)` is the full signature). Cleanup must live in the lifespan body's `finally`:

```python
@asynccontextmanager
async def lifespan(app):
    await app.warm_async_singletons()  # fail-fast on resource opens
    try:
        yield
    finally:
        # Reverse-of-open order. Sqlite last — others may need cache.
        c = app.container()
        for type_, closer in (
            (LlmExtractorHandle, _close_llm),
            (BrowserPool, lambda p: p.close()),
            (aiosqlite.Connection, lambda conn: conn.close()),
        ):
            try:
                instance = c.resolve(type_)  # sync after warm
                await closer(instance)
            except Exception as exc:
                # Log via a2kit.ldd at error level; don't strand siblings.
                ...

async def _close_llm(handle: LlmExtractorHandle) -> None:
    if handle.extractor is not None:
        await handle.extractor.close()
```

The closer-table pattern keeps the lifespan body short and the close logic per-resource explicit. If the LlmExtractorHandle has no live extractor, `_close_llm` no-ops.

### Why explicit closers vs a singleton-teardown API

We want the singleton-teardown API (it'd let factories own their close), but it doesn't exist in v0.32. Worth raising in the next a2kit feedback round:

> Suggested round-7 wish: `app.singleton(T, factory, teardown=fn)` — fn invoked at lifespan exit, error-isolated per-singleton. Removes the explicit lifespan-body cleanup pattern that every consumer with async resources is now hand-rolling.

For now, the closer-table pattern in `server.py` works and is honest about the dependency order.

### Why pre-`yield` warm matters

Without `await app.warm_async_singletons()`, the first tool invocation pays the resource-open cost (and surfaces any open errors). With it, errors surface at startup — same fail-fast property our `@on_startup` had. Cheap, idempotent, no reason not to.

---

## Decision 3 — Router contract: `slug` + `tools` ClassVars (NEW for v0.31+)

v0.31 removes `_derive_slug` and the `dir(self)` walk for tools. Both must be declared explicitly. Verified from `src/a2kit/routers.py`: missing `slug` raises `TypeError` at `Router.__init__` time naming the subclass; missing `tools` raises similar.

### Migration

```python
# routers.py — current shape
class WebRouter(a2kit.Router):
    """Routes web-fetch tools."""

    @a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
    async def fetch(self, *, url: str, ...) -> FetchResponse:
        ...

# routers.py — v0.32 shape
class WebRouter(a2kit.Router):
    """Routes web-fetch tools."""

    slug: ClassVar[str] = "web"          # required
    visibility: ClassVar[str] = "all"     # default; explicit for clarity (optional)

    @a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
    async def fetch(
        self,
        *,
        url: Annotated[str, pydantic.Field(description="Absolute http(s) URL to fetch.")],
        ...,
    ) -> FetchResponse:
        ...

    tools: ClassVar[tuple[Callable[..., Any], ...]] = (fetch,)  # required, AFTER methods
```

Two gotchas surfaced by the source:
- `tools` MUST be placed AFTER the `fetch` definition. Class-body order matters because `tools = (fetch,)` reads the unbound function via the class namespace. If placed before, `fetch` is undefined.
- A decorated-but-unlisted method silently does NOT register. The CHANGELOG mentions a follow-up lint rule for this drift; for now, the wire-format completeness test (Decision 5) catches it indirectly because the missing tool's params won't appear in `_meta.list_tools`.

a2web has only one router with one tool, so the gotchas barely apply. For future routers, document the order in CLAUDE.md.

### Router-level lifespan? No.

`Router.lifespan` is the per-router contract for resource setup. a2web is single-router and the resources are app-scoped (sqlite, browser pool, extractor). Putting the lifespan on `WebRouter` would couple the resources to one router; if we later add a second router (e.g. `_meta.*` health surface), they'd want the same resources. Keep lifespan at App level.

---

## Decision 4 — `a2kit.Param` → `pydantic.Field` (NEW for v0.31+)

Mechanical replacement, 6 sites in `routers.py`. Migration regex per the v0.31 CHANGELOG:

```
positional:  a2kit.Param("desc")          → pydantic.Field(description="desc")
keyword:     a2kit.Param(description=…)   → pydantic.Field(description=…)
```

The wrapper was a one-line forwarder; behavior identity at the kwargs level. No semantic risk.

### Style note — Annotated wrapping is now the *only* way

With docstring-pull reverted (v0.30) and `a2kit.Param` removed (v0.31), the only ways to attach a parameter description to the MCP schema are:
1. `Annotated[T, pydantic.Field(description="...")]`
2. Pydantic `Field` directly on a `body: BaseModel` parameter

For our `WebRouter.fetch`, all params are primitives, so option 1 is the only path. Verbose but explicit — and we can verify completeness with a wire-format test (Decision 5).

The previous proposal's pydocstyle convention pin and CLAUDE.md docstring style note are obsolete. Drop both.

---

## Decision 5 — Param-description completeness test (CARRIED FORWARD)

The v0.29.0 `TestClient.call_wire` survives. The completeness test originally proposed against docstring-pull drift now guards against the OPPOSITE drift mode: contributors forgetting `pydantic.Field(description=...)` on a new param.

```python
# tests/test_router_schema.py
async def test_fetch_params_have_descriptions(client):
    """Every user-facing fetch param has a substantive MCP schema description.

    Belt-and-braces: if a contributor adds a new kw-only param to
    WebRouter.fetch without an Annotated[T, pydantic.Field(description="...")]
    wrapper, this test fails.
    """
    schema = await client.call_wire("_meta.describe_tool", name="WebRouter.fetch")
    props = schema["inputSchema"]["properties"]
    for name in ("url", "include_links", "link_roles", "debug", "wrap_content", "ask"):
        desc = (props.get(name) or {}).get("description") or ""
        assert len(desc) >= 20, (
            f"WebRouter.fetch param {name!r} has weak/missing description "
            f"in MCP schema (got: {desc!r}). Wrap with "
            f"Annotated[T, pydantic.Field(description=...)]."
        )
```

Verify the exact `_meta` introspection path against the v0.32 README before locking the test (it might be `_meta.schema` or `_meta.list_tools` + projection). The principle holds: assert against the wire shape, not against the source code.

---

## What `server.py` looks like post-migration

```python
"""a2web server entrypoint — a2kit v0.32 composition."""

from contextlib import asynccontextmanager

import aiosqlite
import a2kit
import a2kit.ldd

from .events import otel_sink
from .events.types import StageEnded, StageStarted, TierEnded, TierHeartbeat, TierStarted
from .llm_resource import LlmExtractorHandle, build_llm_extractor
from .packages.browser_pool import BrowserPool, build_browser_pool
from .packages.http_cache import open_sqlite_with_schema
from .routers import WebRouter
from .settings import AppSettings
from .state import AppState, build_state


@asynccontextmanager
async def lifespan(app):
    """App lifespan — fail-fast warm + LIFO resource cleanup.

    Replaces the v0.27-era @on_startup / @on_shutdown pair (removed in
    a2kit v0.31). warm_async_singletons surfaces sqlite open errors at
    startup; the finally block closes resources in reverse-of-open
    order, with each close error-isolated so one failure doesn't strand
    siblings.
    """
    await app.warm_async_singletons()
    try:
        yield
    finally:
        c = app.container()
        # LIFO order; sqlite last (others may rely on cache).
        for type_, closer in (
            (LlmExtractorHandle, _close_llm),
            (BrowserPool, lambda p: p.close()),
            (aiosqlite.Connection, lambda conn: conn.close()),
        ):
            try:
                instance = c.resolve(type_)
                await closer(instance)
            except Exception as exc:
                # One sink line per failure; no re-raise.
                ...


async def _close_llm(handle: LlmExtractorHandle) -> None:
    if handle.extractor is not None:
        await handle.extractor.close()


app = a2kit.App("a2web", health_tool=True, lifespan=lifespan)
app.add_router(WebRouter())

# Singletons — async factories; resolved on first inject or warm.
app.singleton(AppState, build_state)
app.singleton(aiosqlite.Connection, factory=open_sqlite_with_schema)
app.singleton(BrowserPool, factory=build_browser_pool)
app.singleton(LlmExtractorHandle, factory=build_llm_extractor)

# Typed event payloads.
for event_type in (TierStarted, TierEnded, StageStarted, StageEnded, TierHeartbeat):
    app.ldd.events.register(event_type)

# OTel sink — sequential after wire emit, best-effort under cancel.
app.ldd.add_sink(otel_sink)


@app.health_check
async def _check_sqlite(sqlite: aiosqlite.Connection) -> a2kit.HealthResult:
    """Readiness probe for `_meta.health` / `a2web health`."""
    try:
        # Cheap query against an always-present sqlite_master row.
        await sqlite.execute("SELECT 1").close()
    except Exception as exc:
        return a2kit.HealthResult.fail(f"sqlite probe failed: {exc}")
    return a2kit.HealthResult.ok()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
```

Net delta vs current: ~20 LOC added (lifespan + closer table) but ~15 LOC removed (`@on_startup` + `@on_shutdown` + their docstrings + the `state.sqlite._ensure()` ceremony in health). Wash.

---

## Migration order recap

```
0. Pin bump  +  verify Union-as-key behavior for app.singleton
1. ctx ambient migration (forced; AmbientContextMissing surfaces drift)
2. Resource collapse → app.singleton + AppState shrink
3. server.py rewrite: lifespan + warm + closer table
4. Router contract: slug + tools ClassVars on WebRouter
5. Param → pydantic.Field migration (6 sites)
6. Test override sweep (replaces monkeypatch.setattr)
7. Import-path audit (LddEmission/LddSink, exception subclasses)
8. New wire-format completeness test
9. Smoke: make check + a2web serve + Claude Code MCP registration
10. Doc closeout
```

Order rationale:
- Step 0 must come first; Union-as-key flag affects step 2's shape.
- Step 1 first among breaking changes — most call sites; failures are loud (AmbientContextMissing).
- Step 2 → 3 — resource collapse must precede lifespan rewrite (lifespan references the singletons).
- Step 4 → 5 — Router contract change (slug/tools) and Param→Field both touch routers.py; do them in one editing pass.
- Step 7 import-audit can move anywhere after step 1; placed late to catch any new imports introduced by steps 2-5.
- Step 9 is the acceptance gate.

---

## Out-of-scope decisions, captured

- **Streaming response API** and **`timeout=` decorator kwarg** stay in `docs/history/A2KIT_WISHES_DEFERRED.md`.
- **`visibility=` adoption** — a2web defaults to `"all"`; no explicit migration. If `visibility: ClassVar[str] = "all"` proves boilerplate-heavy, drop and rely on default.
- **`Router.lifespan` adoption** — single-router app, no per-router resources; keep lifespan at App level.
- **`A2KitMetaExtras` introspection** — a2web doesn't read meta.extra anywhere (verified via grep). No migration needed.
- **Behavior changes to fetcher logic** — none. Tier order, cache rules, escalation paths are unchanged.
- **New tools** — none. This is a substrate migration.

---

## Wishes for next a2kit feedback round (round 7)

Captured here so they're not lost; will be moved to `docs/history/A2KIT_WISHES_DEFERRED.md` at migration close-out:

1. **`app.singleton(T, factory, teardown=fn)`** — singleton-owned cleanup. The closer-table pattern in `server.py` is a workaround that scales linearly with resource count.
2. **Decorator-time enforcement of `tools` tuple completeness.** v0.31 silently doesn't register decorated-but-unlisted methods. The CHANGELOG mentions a follow-up lint rule; track its arrival.
3. **Singleton key support for `Optional[T]` / `T | None`.** Verify in step 0; if it's "use a Handle dataclass forever," that's worth flagging explicitly.
