## Context

a2kit v0.23 exposes typed DI via `App.provide(type_, factory=None)`. Tools declare a kwarg of the registered type and the container resolves it on dispatch. Without `connections_cli` (option B from PR1), there is no auto-installed provider — we register `AppState` ourselves.

Lifespan hooks in a2kit are minimal: `build_mcp_server(app, **fastmcp_kwargs)` forwards `lifespan=` to FastMCP, but the lazy `serve` command in `a2kit.packages.mcp.cli` calls `build_mcp_server(app)` with no kwargs. Threading a lifespan through `a2kit.run(app)` requires either patching `serve_command` ourselves or waiting for an a2kit hook. Neither is needed in PR2 — the resources we'd manage in a TaskGroup (sqlite connection pool, NDJSON log writer, breaker registry) all arrive in PR3+. **PR2 ships the seam, PR4 wires the lifespan.**

## Goals / Non-Goals

**Goals:**
- `AppState` exists, is module-scope, and is `@dataclass(slots=True)`.
- Tools can declare `state: AppState` and a2kit's container resolves it.
- Per-App singleton: two `App` instances → two `AppState` instances.
- Existing PR1 tests still pass; new canary test covers the two-app case.
- `make check` green.

**Non-Goals:**
- No `anyio.TaskGroup`, no FastMCP lifespan integration. Deferred to PR4.
- No real resources — `sqlite`, `proxy_pool`, `breakers`, `log_writer`, `browser_pool` are typed `None` placeholders in PR2.
- No CLI-level lifespan hooks. `a2kit.run(app)` stays untouched.
- No state mutation from tools. `AppState` is read-only from tool code in PR2; PR3+ adds setter methods only as resources land.

## Decisions

### Decision 1: per-App singleton via factory closure

a2kit's `app.provide(AppState)` (class-as-factory) instantiates `AppState` per dispatch. We need shared state across calls, so we register a closure that captures exactly one `AppState`:

```python
def register_state(app: a2kit.App, *, settings: AppSettings | None = None) -> a2kit.App:
    state = AppState(settings=settings or get_settings())
    app.provide(AppState, lambda: state)
    return app
```

Two `register_state(App(...))` calls produce two independent states. The closure is a regular Python lambda — no metaclass tricks, no globals, no `lru_cache` (which would scope to the process and break the canary).

**Alternatives considered:**
- `app.provide(AppState)` class-as-factory → fresh instance per call, breaks any caching/pooling guarantee. Rejected.
- Module-level singleton via `lru_cache` → process-scoped, breaks the canary, hides the App boundary. Rejected.
- `contextvars.ContextVar` → per-async-task scoping, wrong granularity, antipattern #21 in a2kit. Rejected.

### Decision 2: Defer lifespan to PR4

The only resources PR2 *could* set up live in TaskGroup-managed loops: NDJSON log writer (PR4), sqlite connection (PR3 — but aiosqlite is per-call), breaker health-check loop (PR7). PR3 lands sqlite as a per-call connection (no TaskGroup needed); PR4 needs a long-lived writer task and is the natural place to introduce the TaskGroup pattern. Trying to wire a TaskGroup in PR2 with no consumers is build-for-imagination.

The TaskGroup integration plan is captured here so PR4 has a clear path: build a custom `serve_command` that calls `build_mcp_server(app, lifespan=our_lifespan)` and replaces the lazy default. Document also the CLI path (CLI tool calls don't currently go through a lifespan; we'll need a helper context manager in `cli.py` that wraps `a2kit.run`).

### Decision 3: `AppState` is `@dataclass(slots=True)`, not pydantic

`AppState` is internal to the pipeline — it is never serialized over the wire, never an MCP return type, never a tool parameter coming from JSON. Pydantic adds validation overhead and a heavier object footprint we don't need. `slots=True` saves memory and prevents typos (no dynamic attribute attachment). This matches `CLAUDE.md`: *"`dataclass(slots=True)` for internal pipeline objects; pydantic only at API boundaries."*

`AppSettings` (pydantic-settings) is the only pydantic object reachable from `AppState` — that's by design, since settings are loaded from external sources (env, YAML).

### Decision 4: Placeholder fields are typed and `None`-defaulted

`AppState` carries typed `Optional[...]` fields for resources that arrive in later PRs:

```python
@dataclass(slots=True)
class AppState:
    settings: AppSettings
    sqlite: aiosqlite.Connection | None = None       # PR3
    log_writer: LogWriter | None = None              # PR4 (forward-decl typing only)
    proxy_pool: ProxyPool | None = None              # PR7
    breakers: BreakerRegistry | None = None          # PR7
    browser_pool: BrowserPool | None = None          # PR7
```

We import the types lazily (under `TYPE_CHECKING`) for the placeholders that don't yet exist. This forces every PR3+ to fill the slot rather than introduce a new field — and the `ty` type checker catches typos immediately.

**Alternatives considered:**
- A `dict[str, Any]` "extras" bag → opaque, kills static checking. Rejected.
- Lazy attribute attachment without `slots` → silently allows typos. Rejected.

### Decision 5: Tool signature gains `state: AppState`

The stub `fetch` tool declares `state: AppState` even though PR2 doesn't use it for any real work. This (a) forces the DI wiring to be exercised in tests, (b) prevents the pattern from drifting in subsequent PRs, and (c) gives PR3 a one-line edit ("read `state.sqlite`") instead of a signature change.

We still return `FetchResponse` with `tier="stub"`. The placeholder reads one harmless field — `state.settings.diagnostics_default` — to confirm the resolution worked, and writes that into the `narrative` for visibility.

## Risks / Trade-offs

- **[Risk] Per-App singleton via closure is "framework-y"** — readers expect a `lru_cache` or a class attribute. Mitigation: name the helper `register_state(app, settings=...)`, document inline why it's a closure (canary requirement), and keep it ≤10 lines. A senior reader can reproduce the pattern.
- **[Risk] Tools depend on `AppState` before any resource lands** — e.g., a PR3 author reads `state.sqlite` and finds it `None`. Mitigation: PR3's first commit *must* include the sqlite field initialization (lifespan in PR3 if needed; otherwise lazy `aiosqlite.connect` on first use). The typed `None` default is a tripwire, not a hiding place.
- **[Risk] FastMCP lifespan is needed earlier than PR4** — if we discover a sqlite connection genuinely needs a TaskGroup before PR4, we revisit. Mitigation: PR3 tests for the cache will surface this in <1 day. We rewind to PR2 and add the lifespan if needed (bounded blast radius — only `state.py` and `server.py` change).
- **[Risk] `AppSettings` is initialized at import time via `get_settings()`** — a test that wants to inject a custom settings must pass `settings=` to `register_state`. Mitigation: `register_state(app, settings=...)` is the single seam; tests use it.

## Migration Plan

- No data migration. PR2 adds a kwarg to one tool; existing MCP clients see no behavior change (the tool result is unchanged in shape and content).
- Rollback: revert PR2 commit — tools lose their `state` kwarg, the placeholder narrative goes back to PR1's static string. No persisted artifacts.
