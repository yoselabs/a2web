# Design — a2kit v0.29 migration

Three decisions need explicit framing before the mechanical work starts. Everything else is a grep-and-replace driven by tasks.md.

---

## Decision 1 — async-singleton shape for each resource

a2kit v0.29.0 ships `app.singleton(T, async_factory)` where the factory is `async def`, the first resolution awaits, and subsequent resolutions return the cached instance synchronously. Per-type `asyncio.Lock` coalesces concurrent first-resolves. This replaces our hand-rolled `_ensure()` + Lock pattern.

The migration question is **what type `T` becomes for each of our three resources** — the underlying handle, or a thin wrapper that owns domain methods.

### `SqliteResource` → `aiosqlite.Connection`

**Collapse to the underlying handle.**

Today's `SqliteResource` exists purely for the lazy-open lifecycle. It owns no domain methods; consumers either `await resource._ensure()` then use the connection directly, or call standalone functions like `cache_get(conn, ...)` / `cache_put(conn, ...)` defined in `packages/http_cache`.

Migration:

```python
# packages/http_cache.py  (factory stays here)
async def open_sqlite_with_schema(settings: AppSettings) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(settings.cache_db_path)
    await _apply_schema(conn)
    return conn

# server.py
app.singleton(aiosqlite.Connection, factory=open_sqlite_with_schema)

# AppState
@dataclass(slots=True)
class AppState:
    settings: AppSettings
    sqlite: aiosqlite.Connection      # was: sqlite: SqliteResource
    browser_pool: BrowserPool
    llm_extractor: Extractor | None
```

Phases inject the connection directly via the existing `state: AppState` route, e.g. `await cache_get(state.sqlite, url, profile_hash)` — drop the `_ensure()` ceremony.

LOC delta: `SqliteResource` class deleted (~25 LOC).

### `BrowserPool` → keep the wrapper class

**Keep `BrowserPool` as the registered type.**

Reasoning: `BrowserPool` is not just a lazy-open shim. It owns:
- `acquire(url)` returning an async context manager that issues a fresh Camoufox context per URL
- per-host concurrency caps
- pool sizing, idle eviction
- circuit breaker integration (purgatory)

These are domain semantics, not DI plumbing. Collapsing to "give me a launched Camoufox" loses those. So we migrate `BrowserPool` *internally* to use a2kit's async singleton for its own bootstrap (one launched Camoufox instance behind the pool), but the pool itself stays the registered DI type.

Migration:

```python
# packages/browser_pool.py
async def build_browser_pool(settings: AppSettings) -> BrowserPool:
    pool = BrowserPool(settings=settings)
    await pool._launch_browser()    # was: deferred to first _ensure()
    return pool

# server.py
app.singleton(BrowserPool, factory=build_browser_pool)
```

The internal `asyncio.Lock` + `_ensure()` inside `BrowserPool` collapse — a2kit owns the first-init synchronization now. The domain methods (`acquire`, host caps, eviction) stay.

LOC delta: ~20 LOC of double-checked-locking inside `BrowserPool` deleted. Class survives.

### `LlmExtractorResource` → `Extractor | None`

**Collapse to `Extractor | None`** — the wrapper is pure plumbing.

Today's `LlmExtractorResource` returns `Extractor | None` based on:
- whether the `[llm]` extra is installed (import check)
- whether the configured provider has credentials available
- whether construction succeeded

The whole thing is "build an extractor or return None with an `_unavailable_reason`." We need `app.singleton` to handle the optional case.

Per the v0.29 CHANGELOG, the factory returns whatever the type annotation says. So:

```python
# llm_resource.py
async def build_llm_extractor(
    settings: AppSettings,
    sqlite: aiosqlite.Connection,
) -> Extractor | None:
    if not _llm_extra_installed():
        return None
    if not _credentials_available(settings):
        return None
    try:
        return await _construct_extractor(settings, sqlite)
    except ExtractorUnavailable:
        return None

# server.py
app.singleton(Extractor | None, factory=build_llm_extractor)
# (or however v0.29 spells "register an Optional type" — verify against
#  released API docs during step 0; falls back to a sentinel if Union types
#  aren't supported as singleton keys.)
```

Open question (verify during task 0a): does `app.singleton` accept `Extractor | None` as the key type, or do we register `Extractor` with a "may return None" annotation? If `Union` keys aren't supported, fallback is a tiny `LlmExtractorHandle` dataclass with `extractor: Extractor | None` and `unavailable_reason: str | None`. We lose nothing functional; just slightly more verbose. Pick after reading v0.29 README's testing/override section.

**Tests:** `state.llm_extractor` is the primary override target — `TestClient.override(Extractor, FakeExtractor())` if Union-as-key works, else `TestClient.override(LlmExtractorHandle, ...)`.

LOC delta: ~30 LOC of `LlmExtractorResource` deleted (or replaced with the ~8 LOC handle dataclass).

---

## Decision 2 — `ctx` migration is mechanical but ordering matters

16 `a2kit.ldd.event(ctx, ...)` call sites in `fetcher.py`. The migration is a single sed-style sweep, but ordering within the task list matters:

1. **Bump the pin first** — v0.29 raises `AmbientContextMissing` outside dispatch. If we strip `ctx` args before the pin, tests that bypass the dispatcher (running phase functions directly via the in-process client) silently no-op LDD; after the pin, they raise. Get the loud-failure behavior in place before we start touching call sites.
2. **Migrate `fetch()` entrypoint and remove the `null_context()` branch** — once the pin is bumped, that branch is unreachable wisdom.
3. **Strip `ctx` from phase function signatures and call sites in one commit** — partial migration creates a state where some functions take `ctx` and pass it to others that don't; messy intermediate states are worse than one atomic sweep.
4. **Re-run the test suite, fix any `ldd_state_for_call(...)` test sites** to add `ctx=` kwarg. Per CHANGELOG, this is the only test seam.

### What about the existing "no ctx → no events" test?

`tests/test_fetcher.py:283` — `"No ctx → no events emitted (a2kit.ldd.event is a no-op without a ctx)."`

The semantics this test encodes are gone. Three options:

1. **Delete it.** The behavior it tested (silent no-op without ctx) no longer exists; v0.29 raises. The test was checking a property of a2kit, not a property of a2web fetcher.
2. **Rewrite to assert the raise.** `with pytest.raises(AmbientContextMissing): await fetch(...)` — but this requires constructing a call path that *bypasses* a2kit's dispatch, which is contrived.
3. **Repurpose: assert the dispatch *binds* ctx.** Call via `TestClient` and assert events emit. This is the *positive* form of the same property.

**Pick #1.** This is an a2kit-side property; we don't need to re-test it. If we want event-emission coverage, option #3 is a separate test ("events emit during a normal fetch path").

---

## Decision 3 — docstring pull guard rails (the load-bearing change)

The Annotated → docstring migration is the only step where bad practice can drift silently. Three guards must ship in the same change:

### Guard 1 — pin Google style

```toml
# pyproject.toml
[tool.ruff.lint.pydocstyle]
convention = "google"
```

a2kit's auto-pull is Google-style only. Numpy / reST formats silently fail. The Ruff rule catches `:param url: ...` etc. at lint time.

### Guard 2 — wire schema completeness test

Using v0.29.0's new `TestClient.call_wire`:

```python
# tests/test_router_schema.py
async def test_fetch_params_have_descriptions(client):
    """Every user-facing fetch param has a substantive MCP schema description.

    Belt-and-braces against docstring drift: if a contributor adds a new
    kw-only param to WebRouter.fetch without updating the Args: docstring
    section, this test fails.
    """
    schema = await client.call_wire("_meta.describe_tool", name="WebRouter.fetch")
    props = schema["inputSchema"]["properties"]
    user_facing = [
        "url", "include_links", "link_roles", "debug", "wrap_content", "ask",
    ]
    for name in user_facing:
        desc = props.get(name, {}).get("description") or ""
        assert len(desc) >= 20, (
            f"WebRouter.fetch param {name!r} has weak/missing description "
            f"in MCP schema (got: {desc!r}). Update the Args: section in "
            f"the fetch() docstring."
        )
```

Verify against the actual v0.29.x `_meta` tool names / schema introspection path during step 4c — the exact wire shape may differ from this sketch. The principle holds.

### Guard 3 — CLAUDE.md style note

Single line under the conventions block:

> `Args:` prose in `@a2kit.read/list_/write`-decorated tools is **agent-facing tool guidance**. Include heuristics (when to pass, when not, payload cost, default rationale), not just type restatement.

Sets the cultural baseline. Reviewers reading docstrings know what to look for.

### Why these three together

Skipping any one creates a drift mode:
- No Guard 1 → contributors instinct-write reST docstrings → silent description loss
- No Guard 2 → param added without Args: entry → silent description loss
- No Guard 3 → Args: prose smooths to type-restatement over time → quality erosion

The migration's `~50 LOC` delete is dwarfed by the long-term cost of any of those drifts. The guards make the delete safe.

---

## What `AppState` looks like after the migration

```python
# src/a2web/state.py  (post-migration, ~25 LOC)
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite

from .packages.browser_pool import BrowserPool
from .settings import AppSettings

if TYPE_CHECKING:
    from .packages.llm_extract import Extractor


@dataclass(slots=True)
class AppState:
    settings: AppSettings
    sqlite: aiosqlite.Connection
    browser_pool: BrowserPool
    llm_extractor: Extractor | None


def build_state(settings: AppSettings) -> AppState:
    """Construct AppState with resource handles unset.

    Resources are resolved lazily by a2kit's async-singleton DI; build_state
    just provides the struct shape. Settings is the only field populated
    eagerly because it's pure config.
    """
    return AppState(
        settings=settings,
        sqlite=None,           # type: ignore[arg-type]  # filled by DI on resolve
        browser_pool=None,     # type: ignore[arg-type]
        llm_extractor=None,
    )
```

Wait — this contradicts the proposal's "non-Optional fields" stance. Two paths:

**Path A:** AppState is a thin marker; DI patches the fields when phases inject AppState. Type-ignored construction. Ugly.

**Path B:** Don't keep resources on AppState at all. Phases inject the resources directly as separate kwargs alongside `state`:

```python
async def _phase_cache_check(
    fc: FetchContext,
    *,
    state: AppState,
    sqlite: aiosqlite.Connection,
) -> None:
    fc.cached_row = await cache_get(sqlite, fc.url, fc.profile_hash)
```

a2kit's container injects what the function signature asks for. AppState collapses to `settings: AppSettings` plus any pure config / mutable per-app state.

Path B is cleaner. AppState becomes:

```python
@dataclass(slots=True)
class AppState:
    settings: AppSettings
```

…and the resources live entirely as a2kit-managed singletons, never reachable via AppState. The orchestrator phases gain a few more kwargs.

**Decision: Path B**, finalized in tasks.md. Side benefit: tests stop touching `state.<resource>` entirely — `TestClient.override` covers it.

---

## Migration order recap

```
0. Pin bump  →  test suite runs (likely red on ctx + null_context)
1. ctx migration (forced loud failures)
2. Resource collapse → app.singleton + AppState reshape (Path B)
3. Test override sweep (replaces monkeypatch.setattr)
4. Docstring pull + 3 guards (last, most discretionary)
5. Smoke checks (CLI fetch + MCP serve + global Claude Code registration)
```

Pin bump is the only step that must come first. 1 must precede 2 (we'd reshape resources twice otherwise). 3 must follow 2 (override targets the new types). 4 is independent of 1-3 and can move earlier if convenient.

---

## Out-of-scope decisions, captured

- **Streaming response API** and **`timeout=` decorator kwarg** stay in `docs/history/A2KIT_WISHES_DEFERRED.md`.
- **Behavior changes to fetcher logic** — none. Tier order, cache rules, escalation paths are unchanged.
- **New tools** — none. This is a substrate migration.
