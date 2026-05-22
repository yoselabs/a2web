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

After running the quality gate on each tier's result, the orchestrator SHALL inspect `gate_result.suggested_tier`. When `suggested_tier == "browser"`, the orchestrator SHALL dispatch the browser tier (looked up in `REGISTRY`) as the next step, regardless of its absence from `TIER_ORDER`. Intermediate `TIER_ORDER` slots SHALL be skipped — they would block on the same signal. Browser dispatches SHALL be capped at 1 per fetch via a per-fetch `browser_dispatches` counter on the orchestrator stack.

When `suggested_tier == "tls_impersonate"` and the producing tier is `raw`, the orchestrator SHALL no-op (raw already uses curl_cffi). When `suggested_tier == "tls_impersonate"` and the producing tier is something else, the orchestrator SHALL fall back to the next `TIER_ORDER` slot (raw).

#### Scenario: Anubis at jina tier triggers browser dispatch, skipping archive

- **WHEN** raw fails, jina returns 200-OK but gate detects Anubis with `suggested_tier == "browser"`
- **THEN** the orchestrator dispatches the browser tier next, the archive tier is not invoked, and `browser_dispatches == 1`

#### Scenario: Browser dispatch capped at 1 per fetch

- **WHEN** the browser tier itself returns a result whose gate verdict still suggests browser (pathological case)
- **THEN** the orchestrator does NOT dispatch the browser tier a second time; the cascade returns `failed` with the last gate verdict

#### Scenario: tls_impersonate after raw is a no-op

- **WHEN** the raw tier produces a Cloudflare interstitial and gate sets `suggested_tier == "tls_impersonate"`
- **THEN** the orchestrator does not retry raw (already curl_cffi); it advances to the next `TIER_ORDER` slot (jina)

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

After each tier produces a result, the orchestrator SHALL consult `next_action_after_tier(tier_result, current_url, settings)`:

- `RewriteUrl(new_url)` — restart the tier loop with `new_url`. Capped at 1 rewrite per fetch (per-fetch counter `url_rewrites`). Subsequent rewrites SHALL be ignored.
- `RetryViaArchive(url)` — dispatch the archive tier as in the after-gate path. Shares the existing `archive_dispatches` cap (1 per fetch); after-tier and after-gate are mutually exclusive paths.
- `Skip` / `None` — no-op.

#### Scenario: arxiv pdf rewrites to abs page

- **WHEN** the URL is `https://arxiv.org/pdf/1234.5678` and any tier returns
- **THEN** the playbook returns `RewriteUrl("https://arxiv.org/abs/1234.5678")`, `url_rewrites` increments to 1, the tier loop restarts with the new URL, and the response's `url` field reflects the rewritten URL

#### Scenario: Rewrite cap prevents loops

- **WHEN** a chain of rewrites would otherwise fire twice in one fetch
- **THEN** the second `RewriteUrl` is ignored; the orchestrator continues without restart

#### Scenario: Cloudflare 403 after-tier triggers archive dispatch

- **WHEN** raw returns 403 from a Cloudflare-fronted host (`server: cloudflare`)
- **THEN** `next_action_after_tier` returns `RetryViaArchive`, the archive tier is dispatched out-of-band, and `archive_dispatches` increments to 1

#### Scenario: After-tier and after-gate share archive cap

- **WHEN** after-tier dispatches archive (cap consumed) and a later gate verdict would also dispatch archive
- **THEN** the second dispatch is suppressed; the original gate verdict stands

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

### Requirement: Site handler not_found takes precedence over a downstream failure verdict

A site handler returning `Verdict.not_found` is the most authoritative negative signal in the pipeline — the site expert has confirmed the content is gone. When a site handler returns `Verdict.not_found` during the tier loop AND the fetch ultimately fails (no tier produces gate-passing content), the orchestrator SHALL report `not_found` as the final response verdict, overriding any vaguer failure verdict (`length_floor`, `other`) produced by a downstream generic tier.

This precedence SHALL apply only when the fetch fails. When a downstream tier produces real, gate-passing content (final verdict `ok`), that success SHALL stand unchanged — the precedence rule never overrides a genuine recovery. The rule SHALL be scoped to `not_found`; transient handler verdicts (`rate_limited`, `timeout`, `connection_error`) are not covered.

#### Scenario: Deleted page — handler not_found survives a downstream length_floor

- **WHEN** a site handler returns `Verdict.not_found`, then the raw tier returns HTTP 200 with a thin sub-length-floor body and the gate verdict is `length_floor`
- **THEN** the final `FetchResponse` carries verdict `not_found` (not `length_floor`), and `status` is `failed`

#### Scenario: Downstream recovery still wins over a handler not_found

- **WHEN** a site handler returns `Verdict.not_found`, then a downstream tier returns gate-passing content (final verdict `ok`)
- **THEN** the final `FetchResponse` carries `status` `ok` — the precedence rule does not override the recovery

#### Scenario: No handler not_found leaves the failure verdict untouched

- **WHEN** no site handler returned `Verdict.not_found` during the fetch and the fetch fails with `length_floor`
- **THEN** the final `FetchResponse` carries verdict `length_floor` — the precedence rule does not fire

