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

