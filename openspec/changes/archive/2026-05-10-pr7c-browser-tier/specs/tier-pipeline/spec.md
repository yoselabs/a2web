## ADDED Requirements

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
