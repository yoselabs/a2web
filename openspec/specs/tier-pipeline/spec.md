# tier-pipeline Specification

## Purpose
TBD - created by archiving change pr3-raw-tier. Update Purpose after archive.
## Requirements
### Requirement: Tier protocol

The system SHALL define `Tier` as a `typing.Protocol` in `src/a2web/tiers/__init__.py` with members `name: str` and `async def fetch(self, url: str, *, state: AppState) -> TierResult`. `TierResult` SHALL be a `@dataclass(slots=True)` carrying at minimum: `body: bytes`, `content_type: str`, `status_code: int`, `final_url: str`, `headers: dict[str, str]`, `tier_extras: dict[str, Any]` (default empty), `verdict: Verdict` (default `Verdict.ok`). Tiers MUST NOT raise for routine HTTP failures (4xx/5xx) — they SHALL set `verdict` to the closed-enum value (`connection_error`, `timeout`, `rate_limited`, `not_found`, etc.) and return.

#### Scenario: Tier protocol shape

- **WHEN** static analysis walks `a2web.tiers.__init__`
- **THEN** `Tier` is a `Protocol`, `TierResult` is a `@dataclass(slots=True)`, and both are at module scope

#### Scenario: HTTP error becomes a verdict, not an exception

- **WHEN** a tier encounters a 503 from the upstream host
- **THEN** the tier returns a `TierResult` with `verdict in {Verdict.rate_limited, Verdict.connection_error}`, NOT a raised exception

### Requirement: Tier registry with explicit ordering

The system SHALL expose `TIER_ORDER: tuple[str, ...]` and `REGISTRY: dict[str, Tier]` from `a2web.tiers.__init__`. After PR5, `TIER_ORDER` SHALL begin with `"site_handler"` followed by `"raw"`. The `"site_handler"` slot SHALL dispatch via `match_handler(url)` from `a2web.handlers`; if no handler matches, the slot SHALL emit a sentinel `TierResult` with `tier_extras["no_match"] = True` that the orchestrator interprets as "skip silently — produce no diagnostic row, fall through to the next tier."

#### Scenario: site_handler precedes raw in PR5

- **WHEN** the registry is imported in PR5
- **THEN** `TIER_ORDER == ("site_handler", "raw")` and `len(REGISTRY) >= 2`

#### Scenario: No-match handler dispatch is silent

- **WHEN** the orchestrator runs against a URL no handler matches
- **THEN** the resulting `FetchResponse.diagnostics` contains no entry with `step == "site_handler"`; the first diagnostic row is from `raw` (or whichever next tier ran)

### Requirement: Block pages never enter the cache

The system SHALL run the quality gate after extraction and before any cache write. If the gate verdict is anything other than `Verdict.ok`, the cache write SHALL be skipped and the verdict SHALL be appended to `FetchResponse.diagnostics`.

#### Scenario: Block page is not cached

- **WHEN** the orchestrator processes a response that triggers any block-page regex
- **THEN** no row is inserted into the `cache` table for the URL+profile_hash key

#### Scenario: Failed-status fetch is not cached

- **WHEN** the orchestrator yields `FetchResponse.status == FetchStatus.failed`
- **THEN** no cache row is written

### Requirement: Adaptive duration formatter

The system SHALL define `fmt_dur(ms: int) -> str` in `src/a2web/utils/time.py`. Output rules:

- `ms < 1000` → `"{ms}ms"` (integer)
- `1000 ≤ ms < 7000` → `"{s:.1f}s"` (one decimal)
- `7000 ≤ ms < 60_000` → `"{s}s"` (integer)
- `ms ≥ 60_000` → `"{m}m{s:02d}s"`

Every duration string in the envelope, diagnostics narrative, and operator hints SHALL be produced via `fmt_dur`. Hand-formatted duration strings SHALL NOT appear in `src/a2web/`.

#### Scenario: Sub-second case

- **WHEN** `fmt_dur(420)` is called
- **THEN** the result is `"420ms"`

#### Scenario: 1.0–7.0s case

- **WHEN** `fmt_dur(1900)` is called
- **THEN** the result is `"1.9s"`

#### Scenario: 7–60s case

- **WHEN** `fmt_dur(8000)` is called
- **THEN** the result is `"8s"`

#### Scenario: Minute-plus case

- **WHEN** `fmt_dur(72_000)` is called
- **THEN** the result is `"1m12s"`

#### Scenario: Zero case

- **WHEN** `fmt_dur(0)` is called
- **THEN** the result is `"0ms"` (never `"0.0s"`)

### Requirement: Pre-rendered handler results bypass extraction

The orchestrator SHALL check `tier_result.tier_extras` for a `"pre_rendered"` dict. When present, the orchestrator SHALL use its `content_md`, `title`, `byline`, and `headings` directly and SHALL NOT invoke `extract_markdown`, `find_published`/`find_updated`, or `parse_metadata`. The quality gate SHALL still run on the rendered markdown; the cache write proceeds with the original `body` (typically JSON for handlers).

#### Scenario: Pre-rendered result skips trafilatura

- **WHEN** a handler returns a `TierResult` with `tier_extras["pre_rendered"] = {"content_md": "...", ...}`
- **THEN** the resulting `FetchResponse.content_md` equals the pre-rendered value and the diagnostics list contains no `extract` row

#### Scenario: Gate still runs on pre-rendered markdown

- **WHEN** the pre-rendered `content_md` is shorter than the length floor (<500 chars)
- **THEN** the gate emits `Verdict.length_floor` and the orchestrator marks the response as failed

### Requirement: Orchestrator dispatches browser tier on gate suggested_tier

Browser-tier dispatch SHALL be decided by the planner `decide_next` over the observation log, not by the orchestrator inspecting a gate result inline. When the log carries a gate observation whose evidence maps to browser escalation, `decide_next` SHALL return an `EscalateBrowser` action; the orchestrator executes it by dispatching the browser tier from `REGISTRY` regardless of its absence from `TIER_ORDER`. Because `decide_next` reads the whole log rather than one won tier's gate result, `EscalateBrowser` MAY fire even when no tier produced gate-passing content — a total-failure case the prior gate-gated design could not reach. Browser dispatches SHALL remain capped at 1 per fetch.

A `tls_impersonate` signal observed on the `raw` tier SHALL be a no-op (raw already uses curl_cffi); on any other tier the cascade advances to the next `TIER_ORDER` slot.

#### Scenario: Anubis at jina tier triggers browser escalation

- **WHEN** raw fails, jina returns 200-OK, and the gate observation records an Anubis browser signal
- **THEN** `decide_next` returns `EscalateBrowser`, the orchestrator dispatches the browser tier, and the browser dispatch count is 1

#### Scenario: Browser escalation fires on a total failure

- **WHEN** every live tier fails and no tier produced gate-passing content, but a tier or gate observation records a soft-block / JS-required signal
- **THEN** `decide_next` returns `EscalateBrowser` and the orchestrator dispatches the browser tier

#### Scenario: Browser dispatch capped at 1 per fetch

- **WHEN** the browser tier itself returns a result whose gate observation still carries a browser signal
- **THEN** `decide_next` does NOT return `EscalateBrowser` a second time; the cascade ends failed with the resolved verdict

#### Scenario: tls_impersonate after raw is a no-op

- **WHEN** the raw tier produces a Cloudflare interstitial whose gate observation carries a `tls_impersonate` signal
- **THEN** the cascade does not retry raw; it advances to the next `TIER_ORDER` slot (jina)

### Requirement: Browser-rendered results cache normally

Unlike archive results (which set `tier_extras["from_archive"] = True` and skip cache write), browser-rendered results SHALL be cached under the standard URL+profile_hash key. `tier_extras["from_browser"] = True` is informational; it SHALL NOT cause the orchestrator to skip cache write.

#### Scenario: Browser success writes cache

- **WHEN** the browser tier returns `verdict == Verdict.ok` with `tier_extras["from_browser"] == True`
- **THEN** the orchestrator writes a cache row for the URL+profile_hash key

### Requirement: Orchestrator resolves a proxy route per tier invocation

Before each tier call, the orchestrator SHALL call `pool.acquire(host, tier_name)` and pass the resulting `proxy_url` (or `None`) into the tier. The orchestrator SHALL populate `Diagnostic.proxy` with the resolved proxy id (or `"direct"`) for that tier's diagnostic row.

When `acquire` returns `None` (all proxies dead AND `proxy_required=True`), the orchestrator SHALL skip that tier with a `Verdict.proxy_unavailable` diagnostic and advance to the next `TIER_ORDER` slot. When the tier itself returns `Verdict.proxy_unavailable`, the orchestrator SHALL `report(handle, success=False)` and apply the same skip-or-advance logic.

#### Scenario: Diagnostic carries proxy id

- **WHEN** raw fetch goes through `residential_eu`
- **THEN** the raw diagnostic row has `proxy == "residential_eu"`

#### Scenario: All proxies dead with proxy_required skips tier

- **WHEN** all proxies for raw on host X are quarantined and the rule has `proxy_required=True`
- **THEN** raw is skipped (no fetch attempt), `Verdict.proxy_unavailable` diagnostic recorded, and the orchestrator advances to jina

### Requirement: Orchestrator executes after-tier RewriteUrl and RetryViaArchive

After each tier appends its observation, the orchestrator SHALL call the planner `decide_next(observation_log, caps)` and execute the returned `Action`. The orchestrator SHALL contain no escalation, rewrite, or stop policy of its own. The actions and their per-fetch caps:

- `RewriteUrl(new_url)` — restart the tier loop with `new_url`; capped at 1 rewrite per fetch.
- `RetryViaArchive(url)` — dispatch the archive tier; capped at 1 archive dispatch per fetch (shared with the after-gate archive path).
- `EscalateBrowser` — dispatch the browser tier; capped at 1 per fetch.
- `Continue` — no escalation; advance to the next `TIER_ORDER` slot, or finish.

#### Scenario: arxiv pdf rewrites to abs page

- **WHEN** the URL is `https://arxiv.org/pdf/1234.5678` and any tier returns
- **THEN** `decide_next` returns `RewriteUrl("https://arxiv.org/abs/1234.5678")`, the tier loop restarts with the new URL, and the response's `url` field reflects the rewrite

#### Scenario: Rewrite cap prevents loops

- **WHEN** a chain of rewrites would otherwise fire twice in one fetch
- **THEN** the second `RewriteUrl` is not executed; the cascade continues without restart

#### Scenario: Cloudflare 403 after-tier triggers archive dispatch

- **WHEN** the raw tier returns 403 from a Cloudflare-fronted host
- **THEN** `decide_next` returns `RetryViaArchive`, the archive tier is dispatched, and the archive dispatch count is 1

#### Scenario: The orchestrator holds no escalation policy

- **WHEN** a tier produces a result that historically triggered an inline escalation
- **THEN** the orchestrator escalates only if `decide_next` returns the corresponding action — it contains no escalation decision of its own

### Requirement: Cookie resolution phase precedes the tier loop

The orchestrator SHALL, when `settings.cookie_source != "none"`, resolve the `Lazy[CookieJarResource]` once per fetch BEFORE entering the tier loop, call `get_for_host(host, scheme, path)` for the request URL, and populate two fields on `FetchContext`:

- `cookies: dict[str, str]` — name→value mapping used by raw tier
- `cookies_full: list[Cookie]` — full Cookie objects used by browser tier

Each subsequent tier dispatch SHALL pass the appropriate field as the tier's `cookies` / `cookies_full` kwarg. When `cookie_source == "none"`, neither field SHALL be populated (both default to empty); `Lazy[CookieJarResource]` SHALL NOT be resolved (lazy-first-use preserved).

When the configured URL is rewritten via `RewriteUrl` and the tier loop restarts, cookies SHALL be re-resolved for the new host BEFORE the next tier dispatch.

#### Scenario: Cookie resolution skipped when source is none

- **WHEN** a fetch runs with `cookie_source == "none"`
- **THEN** `CookieJarResource` is not resolved (its `Lazy` thunk remains unevaluated), and `FetchContext.cookies` is the empty dict

#### Scenario: Cookie resolution runs once per fetch

- **WHEN** a fetch runs with `cookie_source == "chrome"` and dispatches both raw and browser tiers
- **THEN** `CookieJarResource.get_for_host` is called exactly once for the original URL's host (rewrite scenarios are separate)

#### Scenario: Cookies re-resolved after URL rewrite

- **WHEN** a fetch starts at `https://example.com/x`, an after-tier action rewrites to `https://other.com/y`, and the tier loop restarts
- **THEN** `CookieJarResource.get_for_host` is called a second time for `other.com`, and the cookies attached to the next tier dispatch correspond to `other.com`

#### Scenario: Empty cookie set produces empty FetchContext fields

- **WHEN** `cookie_source == "chrome"` and `get_for_host` returns `[]` for the host
- **THEN** `FetchContext.cookies == {}` and `FetchContext.cookies_full == []`, and tiers receive no cookies

### Requirement: Stale-cookies operator hint appended exactly once per stale fetch

The orchestrator SHALL consult `CookieJarResource.staleness()` once per fetch when `cookie_source != "none"`. When `staleness().is_stale == True`, the orchestrator SHALL append a single `OperatorHint(code="cookies_stale", message=..., fix="Run `a2web cookies refresh`")` to `FetchResponse.operator_hints` and emit one `a2kit.ldd.event(CookiesStale(profile, browser, age_hours))` for the fetch.

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

### Requirement: State construction goes through a single bootstrap factory

The codebase SHALL expose exactly one async factory `bootstrap_state(settings: AppSettings) -> tuple[AppState, Resources]` in `src/a2web/state.py`. `Resources` SHALL be a frozen dataclass carrying the three Lazy-eligible resources (`browser_pool: BrowserPool`, `llm_extractor: LlmExtractorResource`, `cookie_jar: CookieJarResource`).

Production composition (`server.py`), eval harness (`llm_eval/__main__.py`), and test fixtures (`tests/conftest.py::make_default_state`) SHALL all delegate to this factory. Direct manual construction of `BrowserPool` / `LlmExtractorResource` / `CookieJarResource` outside the factory is forbidden.

A new resource added to the bundle SHALL automatically appear in all three construction paths without per-path edits.

#### Scenario: Production composition uses bootstrap_state

- **WHEN** `server.py` builds the App's provider chain
- **THEN** the resources come from `bootstrap_state(...)`, not from individual ad-hoc constructors

#### Scenario: Eval harness wires browser_pool via bootstrap_state

- **WHEN** `llm_eval/__main__.py` constructs systems for the bench
- **THEN** `BrowserPool` reaches `A2WebDetail` and `A2WebExtract` via the factory's `Resources` bundle, not via a manually constructed pool that could be forgotten (preventing the class of regression that caused the v0.22 bench gap)

#### Scenario: Tests bypass DI but still use the factory

- **WHEN** `tests/conftest.py::make_default_state` is invoked
- **THEN** it returns the `(AppState, Resources)` tuple from `bootstrap_state`, with stubs as needed for resources that tests want to omit

### Requirement: FetchContext exposes Lazy[T] resources as non-optional

`FetchContext.browser_pool`, `FetchContext.llm_extractor`, and `FetchContext.cookie_jar` SHALL be declared as `Lazy[BrowserPool]`, `Lazy[LlmExtractorResource]`, `Lazy[CookieJarResource]` respectively — NO `| None` union. When a direct-call path does not provision a real resource, the caller SHALL pass a stub Lazy whose invocation raises a `ResourceUnavailable` exception carrying an operator-hint-ready reason string.

Phases that consume these resources SHALL NOT check `if fc.<resource> is not None`; instead they SHALL `await fc.<resource>()` and catch `ResourceUnavailable` to emit the operator hint path.

#### Scenario: Production tool invocation passes real Lazy

- **WHEN** WebRouter.ask is invoked through the MCP transport
- **THEN** all three Lazy[T] params resolve to real resources via a2kit DI; no `None` check is required at the phase seam

#### Scenario: Eval harness stub raises operator-hint-ready error when no real pool

- **WHEN** an eval system runs with `Resources(browser_pool=stub)` and a phase awaits the stub
- **THEN** the stub raises `ResourceUnavailable("eval harness not provisioned with BrowserPool")` which the phase catches and converts to `OperatorHint(code="browser_unavailable", ...)`

### Requirement: Verdict is the pure projection of the decision log

`FetchContext.gate_verdict` and `FetchContext.gate_subsystem` (mutable snapshot slots) SHALL be removed. All code that previously read them SHALL read from `fc.resolved_verdict()` or a new pure projection helper `fc.last_gate_outcome() -> GateOutcomeProjection | None` that derives the most recent gate observation from the log.

The decision log (`fc.observations`) remains the single mutable accumulator; the verdict and gate state are pure projections — they cannot diverge from the log.

#### Scenario: Re-gate after browser escalation reflects the new verdict

- **WHEN** a browser escalation completes and `_regate_after_escalation` appends a new `gate_outcome` observation
- **THEN** the subsequent call to `fc.resolved_verdict()` returns the verdict reflecting the new observation, with no separate `gate_verdict` field to keep in sync

#### Scenario: Cache-write gate reads the projection, not a snapshot

- **WHEN** `_phase_cache_write` evaluates whether to write the body to cache
- **THEN** it checks `fc.resolved_verdict() is Verdict.ok` (the projection); no parallel snapshot exists that could disagree

### Requirement: Extraction pipeline returns immutable candidates and selects via a pure function

`_phase_extract` and the extraction escalation ladder (`_run_extraction_escalation`, `_escalate_via_json`, `_escalate_via_records`) SHALL produce `ContentCandidate` values (`@dataclass(frozen=True, slots=True)` with fields `source: Literal["trafilatura","json_synth","record_synth","browser_rerun"]`, `content_md: str`, `headings: list[Heading]`, `links: list[Link]`, `score: int`) instead of mutating `fc.content_md` in place.

Selection across candidates SHALL be performed by a pure function `pick_best(candidates: list[ContentCandidate]) -> ContentCandidate | None` carrying the existing length-aware-for-flat and threading-aware-for-records policy. The orchestrator assigns `fc.content_md` = `pick_best(...).content_md` exactly once per phase invocation, not interleaved with mutation.

#### Scenario: Trafilatura + JSON + record candidates are all generated, best is picked

- **WHEN** `_phase_extract` runs on a record-set-shaped page where trafilatura produces 1500 chars, json_synth produces 0, and record_synth produces 3000 (threaded)
- **THEN** all three `ContentCandidate` instances exist as immutable values, and `pick_best` returns the record_synth candidate; `fc.content_md` is assigned once to that candidate's content_md

#### Scenario: Browser escalation re-runs extraction purely

- **WHEN** a browser escalation produces new raw HTML and the orchestrator re-invokes the extraction pipeline
- **THEN** a fresh list of `ContentCandidate` is generated against the new HTML; the prior `fc.content_md` is replaced (not amended) with the new pick_best result

### Requirement: A handler can escalate to a direct paid site render

A tier result MAY carry an `escalate_to_render` signal. A handler sets it when its optimized route fails (a converting handler's rewritten fetch errors, or a walled surface returns a hard block) but the ORIGINAL URL is still a renderable page. On such a result the orchestrator MUST record the failed attempt as a diagnostic, log a NON-authoritative tier observation (so even a `not_found`/`404` from the handler does not end the run), STOP the free tier ladder (which is fooled by SPA shells that exceed the length floor and by block pages), and dispatch the paid tier (Zyte `browserHtml`) directly onto the original URL. The paid result is then gated like any other tier output. If no paid tier is keyed — or the paid render fails — the fetch MUST surface as retrieval-incomplete with a critical `try_user_browser` operator hint (never-silently-miss), because the free ladder was stopped and the render was the only route.

#### Scenario: Render signal dispatches the paid tier and skips the free ladder

- **WHEN** the site-handler tier returns a result with `escalate_to_render` set for `https://hn.algolia.com/?q=claude`
- **THEN** the orchestrator dispatches the paid tier (Zyte `browserHtml`) on the original URL
- **AND** the free tiers (`raw`, `jina`) are not run
- **AND** on success the paid-rendered content wins the fetch

#### Scenario: A handler placeholder verdict does not end the run

- **WHEN** the handler's `escalate_to_render` result carries verdict `not_found` (e.g. a `404` from a rewritten API)
- **THEN** the observation is recorded as non-authoritative
- **AND** the paid render still proceeds (the `404` does not short-circuit as an authoritative site-handler not_found)

#### Scenario: Render failure is a loud miss

- **WHEN** `escalate_to_render` is requested but no paid tier is keyed (or the paid render fails)
- **THEN** the response has `retrieval_incomplete` set
- **AND** carries a critical `try_user_browser` operator hint
- **AND** does not present the free-tier shell as a successful answer

#### Scenario: The failed attempt is recorded

- **WHEN** a handler escalates via `escalate_to_render`
- **THEN** a diagnostic row for the handler's tier is present in the response (the attempt is observable, not silently dropped)

### Requirement: JSON responses are synthesized in-place, never routed through jina

When a tier returns a 2xx response whose content-type is JSON-family (per the shared `_is_json_content_type` predicate), the orchestrator SHALL treat the JSON body as content: the tier wins (`Verdict.ok`), and `_phase_extract` SHALL synthesize the JSON body to markdown instead of running trafilatura. The orchestrator SHALL NOT escalate a JSON response to the jina (`r.jina.ai`) HTML reader.

Synthesis SHALL proceed as: parse the body via `json_in_script.parse_json_response`; on a `JsonPayload`, render via `domain.json_to_markdown_rows`; install the result as `fc.pre_rendered_payload` so the quality gate's content-type check is bypassed and trafilatura is skipped.

#### Scenario: A JSON API endpoint is synthesized, not escalated

- **WHEN** the raw tier returns HTTP 200 + `application/json` for `https://api.example.com/data` carrying `{"items": [{"title": "A"}, {"title": "B"}]}`
- **THEN** the fetch succeeds with `status == ok`, `content_md` contains the synthesized rows, and no diagnostic records a `jina` tier step

#### Scenario: A recognized JSON shape renders as a table/records

- **WHEN** a JSON response body carries a top-level `products` array of objects with `name` + `price`
- **THEN** `content_md` is the `json_to_markdown_rows` rendering (linked records / table), identical to the JSON-in-script path for the same shape

### Requirement: Unknown-shape JSON falls back to the JSON text, never a false failure

When `json_to_markdown_rows` produces nothing for a parseable JSON body (a shape it does not recognize), the orchestrator SHALL fall back to the JSON text itself as `content_md` — pretty-printed and length-capped — so a valid-but-unrecognized JSON payload reaches the caller and the `ask` extractor. A JSON response SHALL NOT produce a `length_floor` failure on account of the jina HTML reader, and SHALL NOT be silently dropped.

#### Scenario: An unrecognized JSON shape still returns content

- **WHEN** a JSON response body is a valid document of a shape `json_to_markdown_rows` does not recognize (e.g. `{"weather": {"temp": 21, "wind": 4}}`)
- **THEN** `content_md` contains the pretty-printed JSON (length-capped), `status == ok`, and the fetch is not a `length_floor` failure

#### Scenario: A small-but-complete JSON response bypasses the thin-shell length floor

- **WHEN** a JSON response body is a small complete document below the length floor (e.g. `{"count": 42}`)
- **THEN** the quality gate accepts it (`status == ok`) — the length-floor exemption keys strictly on the JSON content-type, not on length or pre-rendered status, so HTML SPA shells keep the full floor

### Requirement: Obstacle-driven render phase

The orchestrator SHALL run an obstacle-driven render phase after answer
extraction (`_phase_extract_answer`) and before the cache write. When the `ask`
extractor reported `obstacle ∈ {empty, blocked}` (the `_INCOMPLETE_OBSTACLES`
set, shared with the retrieval-completeness logic), the phase SHALL dispatch one
paid render of the original URL via the existing `_escalate_paid` path, then —
only if the render produced new content — re-run content extraction and answer
extraction over the rendered content.

The phase SHALL fire only when ALL hold: the `ask` path is active; the obstacle
is in `_INCOMPLETE_OBSTACLES`; `paid_dispatches < 1`; **the already-extracted
content is THIN** (`len(content_md) < _RENDER_CONTENT_CEILING`, 2000 chars — a
content-rich page is complete, so the answer's absence is real and a render
can't add it; this is the load-bearing SSR guard: Next/Nuxt sites carry SPA
mount markers yet already contain their content); the content did NOT come from
a JS-executing tier (`jina` / `browser` / `browser_robust`); AND the raw body
shows unrendered-SPA markers (`block_detector.looks_like_unrendered_spa`). The
shared one-dispatch-per-fetch cap guarantees termination. The phase SHALL NOT
re-run the gate/escalate phase — the paid render is authoritative content, and
the fresh `obstacle` from the re-extraction is the completeness check.

#### Scenario: Thin SPA shell escalates to a paid render

- **WHEN** an `ask` fetch over a JS-shell page (thin `content_md`, unrendered-SPA markers, non-JS tier) passes the gate but the extractor reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier on the original URL and re-runs answer extraction over the rendered content

#### Scenario: Content-rich SSR page with SPA markers does NOT render

- **WHEN** an `ask` fetch over an SSR framework page (SPA mount markers present, but substantial extracted content ≥ the ceiling) reports `obstacle: "empty"` because the answer genuinely isn't present
- **THEN** no paid render is dispatched (the page is complete; a render can't add the missing answer), and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Content from a JS-executing tier does NOT re-render

- **WHEN** the winning content came from `jina` / `browser` / `browser_robust` and the extractor reports `obstacle: "empty"`
- **THEN** no obstacle-driven paid render is dispatched

#### Scenario: Healthy ask does not trigger the phase

- **WHEN** an `ask` fetch reports no obstacle (or an obstacle outside `{empty, blocked}`)
- **THEN** the obstacle render phase is a no-op and no paid egress occurs

### Requirement: Listing-completeness phase and escalation trigger

The pipeline SHALL run a listing-completeness assessment after record extraction:
it compares the parsed record count against the generic item oracle via
`content_expectations.assess` and, on a `partial` verdict, attaches the
`listing_partial` signal. When listing completion is enabled and the partial
listing was served by a non-scrolling tier (raw/jina), the `partial` verdict
SHALL act as an escalation trigger requesting a scrolling render — reusing the
`escalate_to_render` / `_escalate_paid` path and sharing the single
one-paid-dispatch-per-fetch cap with the gate-wall and obstacle triggers. The
phase performs no fetching when completion is disabled (signal-only).

#### Scenario: Completeness phase runs after extraction

- **WHEN** a fetch has extracted records and computed a listing verdict
- **THEN** a `partial` verdict attaches the `listing_partial` signal before the response is built

#### Scenario: Partial listing on a non-scrolling tier escalates

- **WHEN** completion is enabled, the verdict is `partial`, the tier was raw/jina, and no render was yet spent
- **THEN** the pipeline requests a scrolling render through the shared render path and one paid dispatch (at most) is consumed

#### Scenario: Signal-only when completion is disabled

- **WHEN** completion is disabled and the verdict is `partial`
- **THEN** the `listing_partial` signal is attached and no render is dispatched

