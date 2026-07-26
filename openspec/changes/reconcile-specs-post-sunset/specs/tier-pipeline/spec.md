## MODIFIED Requirements

### Requirement: Stale-cookies operator hint appended exactly once per stale fetch

The orchestrator SHALL consult `CookieJarResource.staleness()` once per fetch when `cookie_source != "none"`. When `staleness().is_stale == True`, the orchestrator SHALL append a single `OperatorHint(code="cookies_stale", message=..., fix="Run `a2web cookies refresh`")` to `FetchResponse.operator_hints` and emit one `CookiesStale(profile, browser, age_hours)` event for the fetch via `await a2web.log.info(...)`.

The hint SHALL NOT be appended more than once per fetch even when the tier loop restarts via `RewriteUrl`. The hint SHALL NOT be appended when `cookie_source == "none"`.

The message SHALL include the numeric `age_hours` (or `"never"` if `last_refresh_at is None`) and the configured `cookie_stale_after_hours` threshold so the agent can reason about the gap.

#### Scenario: Stale hint appended once

- **WHEN** a fetch runs stale and the tier loop restarts via `RewriteUrl`
- **THEN** `response.operator_hints` contains exactly one `code == "cookies_stale"` entry

#### Scenario: Never-refreshed message says "never"

- **WHEN** `staleness().last_refresh_at is None` and a fetch completes
- **THEN** the `cookies_stale` hint's `message` field contains the substring `"never"`

#### Scenario: Stale message names age and threshold

- **WHEN** `staleness().age_hours == 72` and `cookie_stale_after_hours == 24`
- **THEN** the `cookies_stale` hint's `message` contains both `"72"` and `"24"`

#### Scenario: No hint when source disabled

- **WHEN** `cookie_source == "none"`
- **THEN** `response.operator_hints` contains no `cookies_stale` entry and `CookiesStale` is not emitted

### Requirement: FetchContext exposes Lazy[T] resources as non-optional

`FetchContext.browser_pool`, `FetchContext.llm_extractor`, and `FetchContext.cookie_jar` SHALL be declared as `Lazy[BrowserPool]`, `Lazy[LlmExtractorResource]`, `Lazy[CookieJarResource]` respectively — NO `| None` union. When a direct-call path does not provision a real resource, the caller SHALL pass a stub Lazy whose invocation raises a `ResourceUnavailable` exception carrying an operator-hint-ready reason string.

Phases that consume these resources SHALL NOT check `if fc.<resource> is not None`; instead they SHALL `await fc.<resource>()` and catch `ResourceUnavailable` to emit the operator hint path.

#### Scenario: Production tool invocation passes real Lazy

- **WHEN** the `query` tool is invoked through the MCP transport
- **THEN** all three `Lazy[T]` resources resolve to real values via the composition-root thunks on `Components`; no `None` check is required at the phase seam (phases `await` the thunk and `try/except ResourceUnavailable`)

#### Scenario: Eval harness stub raises operator-hint-ready error when no real resource

- **WHEN** an eval system runs with a stub `Lazy` in place of a real resource and a phase awaits the stub
- **THEN** the stub raises `ResourceUnavailable("eval harness not provisioned with <resource>")` which the phase catches and converts to `OperatorHint(code="browser_unavailable", ...)`

## REMOVED Requirements

### Requirement: State construction goes through a single bootstrap factory

**Reason**: Described the retired `bootstrap_state(settings) -> tuple[AppState, Resources]`
factory and the `Resources` frozen-dataclass bundle. Both were removed by
`sunset-a2kit-dependency` — the second assembly point was absorbed into the ONE
composition root `components.build_components(...)` (CLAUDE.md: "`bootstrap_state`
and the `Resources` bundle are GONE"). The heavy resources it bundled are now
`Lazy[T]` thunks on the `Components` dataclass.

**Migration**: The single-construction-path invariant is now owned by the
`app-composition` requirement "A single composition root builds every long-lived
resource" (and its "Tests substitute fakes through the same root" scenario, which
replaces the `bootstrap_state`-in-conftest scenarios). The eval-harness and test
wiring go through `build_components(...)` / `make_default_components(...)`.
