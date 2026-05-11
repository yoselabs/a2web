## MODIFIED Requirements

### Requirement: Proxy pool tracks health and fallback chains

The system SHALL provide `ProxyPool` with the existing `acquire(host, tier) -> ProxyHandle | None` and `report(handle, *, success, ms)` contract preserved at the call-site level. Internally, per-proxy health state SHALL be backed by `purgatory.AsyncCircuitBreakerFactory` keyed by proxy URL — the 3-fail/600s state machine is implemented as a purgatory breaker configuration rather than a hand-rolled state machine. This unlocks redis-backed persistence as a future option (currently still in-memory).

The pool's lifecycle SHALL be owned by `@app.on_startup` (constructed in `build_state`, no lazy ensure pattern). The `state.proxy_pool` field is non-optional after startup.

#### Scenario: Three consecutive failures quarantine via purgatory breaker

- **WHEN** `report(handle, success=False, ms=...)` is called three times consecutively for the same proxy
- **THEN** the proxy's purgatory breaker is in `OPEN` state (mapped to `HealthState.quarantined`) with a 600s reset timeout

#### Scenario: Acquire still walks fallback chain on quarantine

- **WHEN** the primary proxy is in `OPEN` state and the fallback chain has an alive proxy
- **THEN** `acquire` returns a handle for the fallback proxy

#### Scenario: Success while quarantined transitions to alive

- **WHEN** the breaker is in `HALF_OPEN` state (post-timeout probe) and `report(handle, success=True, ms=...)` fires
- **THEN** the breaker transitions to `CLOSED` (mapped to `HealthState.alive`)

### Requirement: Route policy resolves a proxy decision per (host, tier)

Contract from v0.1.0 is preserved at the function level (`resolve_route(host, tier, settings) -> ResolvedRoute`, pure, first-match-wins, host-glob, tier composition, `${ENV}` substitution, default-direct fallthrough). The implementation moves to `packages/proxy-pool/src/proxy_pool/policy.py`. The package SHALL define its own narrow types for `ResolvedRoute` (and re-export from its public API) — a2web's `src/a2web/proxy/__init__.py` adapter SHALL translate where needed.

#### Scenario: Policy lives in workspace package

- **WHEN** an operator inspects the file tree
- **THEN** `resolve_route` is defined in `packages/proxy-pool/src/proxy_pool/policy.py` (not `src/a2web/proxy/policy.py`); the existing `src/a2web/proxy/policy.py` is deleted or becomes a re-export from the package

#### Scenario: Existing scenarios continue to pass

- **WHEN** the v0.1.0 test suite for `resolve_route` is rebound to the package import path
- **THEN** all existing scenarios (exact host match, glob host match, tier match, AND composition, explicit direct override, no-match fallthrough) pass against the new package

## ADDED Requirements

### Requirement: proxy-pool is a uv workspace package

The directory `packages/proxy-pool/` SHALL exist with its own `pyproject.toml`, `src/proxy_pool/`, and `tests/`. The package SHALL:

- Declare `purgatory>=...` as its own dependency (not relying on a2web's pin).
- NOT import any symbol from the `a2web` namespace.
- Define its own narrow types (`HealthState`, `ResolvedRoute`, `ProxyHandle`) and expose them via `__init__.py`.
- Pass `make lint`, `make ty`, `make test` independently when run inside the package directory.

#### Scenario: Package isolation

- **WHEN** lint runs over `packages/proxy-pool/src/`
- **THEN** zero `from a2web` or `import a2web` matches are found

#### Scenario: Package tests run independently

- **WHEN** `cd packages/proxy-pool && uv run pytest` runs
- **THEN** the test suite passes without requiring a2web to be installed

### Requirement: a2web adapter for proxy-pool

`src/a2web/proxy/__init__.py` SHALL be a thin adapter that imports `proxy_pool` and translates between package-native types and a2web domain types (e.g., translating package `HealthState` to a2web diagnostic verdict mappings). The adapter SHALL not be a re-export; it SHALL be the seam where domain types arrive.

#### Scenario: Adapter present

- **WHEN** `from a2web.proxy import ProxyPool, resolve_route` runs
- **THEN** the import succeeds; the returned types are package types AND a2web's orchestrator uses the adapter functions to translate to `Diagnostic` rows
