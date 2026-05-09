## 1. State module — `src/a2web/state.py`

- [x] 1.1 Define `AppState` as `@dataclass(slots=True)` with `settings: AppSettings` (required) and `Optional`-typed placeholder fields for `sqlite`, `log_writer`, `proxy_pool`, `breakers`, `browser_pool` (all default `None`)
- [x] 1.2 Use `TYPE_CHECKING` imports for placeholder types that don't exist yet (forward references like `aiosqlite.Connection`); concrete types fill in from PR3+
- [x] 1.3 Implement `register_state(app: a2kit.App, *, settings: AppSettings | None = None) -> a2kit.App` that constructs one `AppState` and registers a closure provider returning it
- [x] 1.4 Inline a one-line comment explaining why we use a closure (canary requirement: per-App singleton, not process-wide)

## 2. Server wiring — `src/a2web/server.py`

- [x] 2.1 Update server composition to chain `register_state(app)` after `add_router(WebRouter())`
- [x] 2.2 Confirm `app.has_provider(AppState)` returns `True` at import time

## 3. Router update — `src/a2web/routers.py`

- [x] 3.1 Import `AppState` from `a2web.state`
- [x] 3.2 Add `state: AppState` kwarg to `WebRouter.fetch`
- [x] 3.3 Use `state.settings.diagnostics_default` in the placeholder narrative ("PR2 stub — diagnostics_default=<value>")
- [x] 3.4 Confirm the MCP-visible schema for `fetch` still lists only `url` (state is DI-resolved, not user input)

## 4. Tests — `tests/test_app_state.py`

- [x] 4.1 Test: `AppState` is a dataclass, has slots, and rejects unknown attributes
- [x] 4.2 Test: `AppState(settings=AppSettings())` initializes with `None` placeholder fields
- [x] 4.3 Test: `register_state(app)` registers a provider; `app.has_provider(AppState)` is `True`
- [x] 4.4 Test (canary): two independent `App` instances each get their own `AppState`; identity comparison fails across them
- [x] 4.5 Test: repeated dispatches on the same App return the same `AppState` instance (identity equality)
- [x] 4.6 Test: `register_state(app, settings=custom)` resolves `state.settings is custom`

## 5. Update PR1 tests — `tests/test_app_composition.py`

- [x] 5.1 Update the `test_fetch_stub_returns_typed_envelope` test so it instantiates a `WebRouter` AND constructs an `AppState` to pass via the `state` kwarg (the router method now requires it)
- [x] 5.2 Add a test that `fetch`'s narrative mentions `diagnostics_default`
- [x] 5.3 Add a test asserting `app.has_provider(AppState)` after `from a2web.server import app`

## 6. CLI / MCP smoke

- [x] 6.1 `uv run a2web --help` still exits 0; `web` and `serve` listed; no `connections`
- [x] 6.2 `uv run a2web web fetch --url=https://example.com` exits 0 and prints a JSON envelope with `tier="stub"` and a narrative containing the `diagnostics_default` value
- [x] 6.3 `uv run a2web serve --transport=stdio` starts; `fetch` schema lists `url` only
- [x] 6.4 Confirm `state` does NOT appear in the MCP `tools/list` input schema for `fetch`

## 7. Quality gate

- [x] 7.1 `make lint` clean
- [x] 7.2 `make ty` clean, zero `# ty: ignore`
- [x] 7.3 `make test` green, coverage ≥85%
- [x] 7.4 `make check` clean

## 8. Docs + commit

- [x] 8.1 Update `CLAUDE.md`: remove the "(PR2)" marker on the `state.py` line; document the closure-singleton pattern in the Conventions section
- [x] 8.2 Update README if it describes tool signatures (probably no change)
- [x] 8.3 Single commit "PR2: AppState dataclass + per-App singleton DI"
- [x] 8.4 Hand off to PR3 (raw tier end-to-end)
