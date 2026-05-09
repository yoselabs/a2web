## Why

PR1 wired `App` composition and the public envelope, but every downstream PR (raw tier, sqlite cache, NDJSON log, browser pool, proxy pool, breaker registry) needs a single shared place to hang long-lived resources. Globals are forbidden by the project rules, so we need DI: a typed `AppState` provider tools resolve via kwarg. PR2 ships the skeleton — the dataclass, the per-App singleton factory, and the canary test that two `App` instances do not share state. Real resources (sqlite, log writer, pools) attach in PR3+; PR2 just locks the seam.

## What Changes

- Add `src/a2web/state.py` with `AppState` (`@dataclass(slots=True)`) holding the resource handles agreed in `CLAUDE.md` (`settings: AppSettings`, plus typed placeholder fields for `sqlite`, `proxy_pool`, `breakers`, `log_writer`, `browser_pool` — all `Optional[...] = None` in PR2).
- Add a per-App singleton factory: `make_app_state(settings: AppSettings | None = None) -> AppState` and a thin `register_state(app, settings=None)` helper that calls `app.provide(AppState, factory)` with a closure capturing exactly one instance for that `App`.
- Update `src/a2web/server.py` to call `register_state(app)` after `add_router(WebRouter())`.
- Update `WebRouter.fetch` to declare `state: AppState` as a DI kwarg. The stub still returns a placeholder `FetchResponse`; it now reads `state.settings.diagnostics_default` (or similar trivial use) to confirm the wire is alive.
- **Canary test**: build two independent `a2kit.App` instances, register state on each, dispatch the `fetch` tool through both, assert each tool saw a different `AppState` instance.
- Document the lifespan deferral: PR2 does NOT wire `anyio.TaskGroup` or FastMCP lifespan. The contract for PR4 (NDJSON log) is captured in `design.md`.
- Add `state.py` to the architecture description in `CLAUDE.md` (already listed) — flip the "(PR2)" comment off.

## Capabilities

### New Capabilities

- `app-state`: per-App typed singleton holding shared resources, exposed to tools via a2kit DI (`state: AppState` kwarg).

### Modified Capabilities

- `app-composition`: `WebRouter.fetch` now declares a `state: AppState` kwarg. Behaviour from PR1's perspective is unchanged (stub return), but the tool signature gains a DI dependency.

## Impact

- **Code**: new `src/a2web/state.py`; modified `src/a2web/server.py`, `src/a2web/routers.py`; new `tests/test_app_state.py`; tweak to `tests/test_app_composition.py` so the existing fetch-stub test passes a fabricated `AppState` (or invokes via a helper that sets up a state-aware app).
- **Public surface**: `AppState` becomes part of the public a2web surface (downstream PRs and tests will import it). Once tools depend on `state: AppState`, removing it is a breaking change for the tool signature.
- **DI**: a2web now uses a2kit's `app.provide(T, factory)` mechanism; no behavioural impact on MCP/CLI shape.
- **Dependencies**: no new top-level dependencies. `anyio` is already in.
- **Performance**: zero — class-as-factory closure is one allocation per App at import.
