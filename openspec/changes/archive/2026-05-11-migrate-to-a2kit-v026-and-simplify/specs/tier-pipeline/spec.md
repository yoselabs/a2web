## MODIFIED Requirements

### Requirement: Tier protocol

The system SHALL define `Tier` as a `typing.Protocol` in `src/a2web/tiers/__init__.py` with members `name: str` and `async def fetch(self, url: str, *, state: AppState) -> TierResult`. `TierResult` SHALL be a `@dataclass(slots=True)` carrying:

- `body: bytes`, `content_type: str`, `status_code: int`, `final_url: str`, `headers: dict[str, str]` — preserved from v0.1.0
- `verdict: Verdict` — preserved (default `Verdict.ok`)
- **Typed extras fields** (replacing `tier_extras: dict[str, Any]`):
  - `pre_rendered: Rendered | None` — populated by site handlers, archive tier on success, and browser tier on success
  - `from_archive: bool` — set by archive tier
  - `snapshot_age_days: int | None` — set by archive tier when available
  - `from_browser: bool` — set by browser tier
  - `js_executed: bool` — set by browser tier
  - `browser_wall_ms: int | None` — set by browser tier
  - `browser_bytes: int | None` — set by browser tier
  - `operator_hint: OperatorHint | None` — set by tiers that surface ops guidance (e.g., browser tier on missing camoufox)
  - `no_match: bool` — set by site-handler dispatcher when no handler matches (silent skip)
  - `skipped: bool` — set by jina tier on deny-list short-circuit (silent skip)
  - `handler_name: str | None` — set by site-handler dispatcher to the matched handler's name (e.g., `"reddit"`)
  - `conditional_hit: bool` — set by raw tier when a conditional GET returns 304

The dict-typed `tier_extras: dict[str, Any]` field SHALL be removed. All tiers SHALL populate the typed fields directly.

Tiers MUST NOT raise for routine HTTP failures (preserved).

#### Scenario: Typed fields, no dict bag

- **WHEN** static analysis walks `a2web.tiers.__init__`
- **THEN** `TierResult` has typed fields for every extras concern AND has no `tier_extras: dict[str, Any]` field

#### Scenario: Site handler populates pre_rendered + handler_name

- **WHEN** any site handler completes successfully
- **THEN** `tier_result.pre_rendered` is a `Rendered` instance AND `tier_result.handler_name` is a non-empty string

### Requirement: Block pages never enter the cache

The system SHALL run the quality gate after extraction and before any cache write. The orchestrator SHALL pass the response to hishel's `controller.handle_response(...)` ONLY when the gate verdict is `Verdict.ok`. Any non-OK verdict (paywall, block_page_detected, anti_bot:*, length_floor, connection_error, etc.) SHALL skip the cache write path entirely and SHALL append the verdict to `FetchResponse.diagnostics`. The cache file SHALL never contain block-page bodies.

#### Scenario: Block page is not handed to cache

- **WHEN** the orchestrator processes a response that triggers any block-page regex (gate verdict ≠ ok)
- **THEN** the hishel `controller.handle_response(...)` call is not made for that fetch AND no cache entry is created

#### Scenario: Failed-status fetch is not cached

- **WHEN** the orchestrator yields `FetchResponse.status == FetchStatus.failed`
- **THEN** no cache write is attempted

## ADDED Requirements

### Requirement: Single archive-dispatch helper

The orchestrator SHALL define `_dispatch_archive(url, *, state, ctx, start_perf, diagnostics) -> ArchiveOutcome` as the single archive-dispatch path. Both the after-tier dispatch (driven by `RetryViaArchive` from `next_action_after_tier`) and the after-gate dispatch (driven by `next_action_after_gate`) SHALL call this helper. `ArchiveOutcome` SHALL carry the fields needed to install archive content into the orchestrator's state (body, content_type, final_url, pre_rendered, status_code, diagnostic row) or indicate "archive failed, keep going."

#### Scenario: Both call sites share the helper

- **WHEN** static analysis walks `a2web.fetcher`
- **THEN** the function `_dispatch_archive` is defined once AND is called from both the after-tier escalation path and the after-gate escalation path AND there are no other archive-dispatch code blocks

#### Scenario: Archive-dispatch cap still enforced

- **WHEN** an orchestrator pass triggers both after-tier and after-gate `RetryViaArchive` candidates
- **THEN** `_dispatch_archive` is called at most once per fetch (the shared `archive_dispatches` counter is checked and incremented inside the helper)

### Requirement: Named phase functions

The orchestrator SHALL be reorganized from a single `_run_pipeline(...)` of ~600 lines into a top-level coordinator (~80 lines) plus named phase functions, each 30–80 lines:

- `_phase_cache_check`
- `_phase_tier_loop`
- `_phase_extract`
- `_phase_gate`
- `_phase_escalate_browser`
- `_phase_escalate_archive`
- `_phase_fit`
- `_phase_cache_write`

Each phase takes a mutable `FetchContext` dataclass (`@dataclass(slots=True)`) and updates it. Decimal phase comments (`# Phase 4.2`, `# Phase 4.25`) SHALL be removed.

#### Scenario: Phase functions exist

- **WHEN** static analysis walks `a2web.fetcher`
- **THEN** each phase function listed above is defined; no comment of the form `# Phase 4.<digit>` remains

#### Scenario: Top-level coordinator is small

- **WHEN** static analysis measures `_run_pipeline`'s LOC
- **THEN** the function body is ≤ 120 lines (down from ~500 in v0.1.0)

### Requirement: Unified tier_used identity

The orchestrator SHALL produce `FetchResponse.tier: str` via exactly one function `_resolve_tier_used(tier_used_context) -> str`. The rule SHALL be:

- Site handler match → `handler_name` (e.g., `"reddit"`, `"hn"`, `"arxiv"`, `"wikipedia"`, `"github"`)
- Otherwise → tier's registry key (`"raw"`, `"jina"`)
- Archive escalation override → literal `"archive"`
- Browser escalation override → literal `"browser"`
- Cache hit → literal `"cache"` (when `cache_state == CacheState.hit` and no tier produced new content)
- None of the above → literal `"none"`

No other code path SHALL assign `FetchResponse.tier`. The orchestrator SHALL set this field exactly once, at the response-build step.

#### Scenario: One writer

- **WHEN** static analysis greps `a2web.fetcher` for `FetchResponse(.+tier=`
- **THEN** exactly one assignment is present (in the final return) AND `_resolve_tier_used` is called there

#### Scenario: Archive escalation overrides

- **WHEN** the orchestrator escalates to the archive tier and recovers content
- **THEN** `FetchResponse.tier == "archive"` regardless of which tier failed earlier

#### Scenario: Site handler wins over registry key

- **WHEN** the site-handler dispatcher matches a Reddit URL
- **THEN** `FetchResponse.tier == "reddit"`, not `"site_handler"`

### Requirement: FetchContext encapsulates orchestrator mutable state

The orchestrator SHALL define `FetchContext` as a `@dataclass(slots=True)` carrying every piece of state that flows between phases (current URL, current body, current content type, current verdict, diagnostics list, escalation counters, etc.). Phase functions read and write fields on the context; they SHALL NOT take many independent parameters.

#### Scenario: FetchContext defined

- **WHEN** static analysis walks `a2web.fetcher`
- **THEN** `FetchContext` is a `@dataclass(slots=True)` at module scope AND phase functions take `ctx: FetchContext` (and `state: AppState`, `ctx: a2kit.ToolContext`) rather than 8+ named parameters

#### Scenario: Per-fetch escalation counters live on FetchContext

- **WHEN** an escalation cap is consulted during a fetch
- **THEN** the counter (e.g., `archive_dispatches`, `browser_dispatches`, `url_rewrites`) is read from and written to `ctx.archive_dispatches` etc. on the FetchContext, not from local function-scoped ints
