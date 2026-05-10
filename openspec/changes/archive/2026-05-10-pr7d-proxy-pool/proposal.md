## Why

PR1–PR7c built the cascade (raw, jina, archive, browser) with tier-internal HTTP clients all going **direct**. The settings model already carries `proxies` and `routes` from day one, but nothing reads them. PR7b also stubbed two playbook actions (`RewriteUrl`, after-tier `RetryViaArchive`) as **computed-but-no-op** — the comment said "PR7c will execute them with the proxy retry layer." PR7c shipped browser-tier instead, so this is the final piece that makes the cascade route-aware and closes the after-tier action no-op.

The two halves are coupled by design: the after-tier `RetryViaArchive` from a Cloudflare-fronted 403 is *exactly* the case where the next attempt usually wants a different exit IP, and `RewriteUrl` (arxiv pdf → abs) is the cleanest test for action-execution wiring. Shipping them together means the orchestrator's per-fetch action loop lands once, in one shape.

## What Changes

- **`proxy/policy.py`**: `RoutePolicy` (settings → resolved decisions). First-match-wins over `routes` table. Match keys: `host` (exact or `*.glob`), `tier` (tier name). Composable AND. Returns `ResolvedRoute(proxy_url: str | None, proxy_required: bool, fallback: list[str])`. Pure function over `AppSettings` + `(host, tier)`.
- **`proxy/pool.py`**: `ProxyPool` (lifecycle-managed; lazy via `state.ensure_proxy_pool`). State per proxy: `alive | quarantined_until(t) | dead`. Methods: `resolve(host, tier) -> ResolvedRoute | None`, `acquire(host, tier) -> ProxyHandle | None` (selects from rule + fallbacks; honors health), `report(handle, *, success, ms)` (updates health, may quarantine on 3 consecutive failures for 10 min). Health state is in-memory only (PR7e adds disk persistence).
- **`proxy/breakers.py`**: thin wrapper around `purgatory` (already a dep). Per-host raw breaker (5 failures → 5 min skip raw for that host), per-proxy breaker (3 consecutive failures → 10 min quarantine). Global breaker deferred (50% of last 100 fetches → emit OTel alarm) — wires hooks but no alerting in PR7d.
- **`tiers/raw.py`**: accept `proxy_url: str | None` plumbed through `curl_cffi.requests.get(..., proxies={"http": ..., "https": ...})`. On `proxy_unavailable` (refused/timeout from proxy), return `Verdict.proxy_unavailable` so the orchestrator can decide: if `proxy_required`, fail the tier; otherwise the orchestrator falls through to the next tier (no silent direct retry).
- **`tiers/jina.py`**: same plumbing via `httpx.AsyncClient(proxy=...)`. Jina-the-SaaS rarely needs proxying (route table will usually leave it direct), but the plumbing is identical.
- **`fetcher.py`**:
  - Resolve route once per tier invocation via `pool.resolve(host, tier_name)`; pass `proxy_url` into raw/jina tiers.
  - Surface `proxy` field on `Diagnostic` rows (proxy id from settings, or `"direct"`).
  - **After-tier action execution** (the deferred PR7b stub): after each tier result, consult `next_action_after_tier`. Honor `RewriteUrl` (capped at 1 per fetch — restart loop with new URL) and after-tier `RetryViaArchive` (capped at 1; same orchestrator branch as the existing after-gate dispatch).
  - Per-fetch counters: `url_rewrites`, `archive_dispatches`, `proxy_swaps`. Caps prevent loops.
- **`state.py`**: `ensure_proxy_pool(state)` async helper, lazy under `asyncio.Lock` like `ensure_browser_pool`. atexit close (no real I/O to flush in v0.1, but symmetric).
- **OTel attrs** (already-imported `opentelemetry-api`): `a2web.route.matched_rule`, `a2web.route.proxy_id`, `a2web.route.fell_back`. Wire under existing `otel_sink` with one extra attr-set per `TierEnded`.
- **TIER_ORDER, REGISTRY**: unchanged. Proxy is a transport detail, not a tier.

## Capabilities

### New Capabilities

- `proxy-pool`: route resolution + per-proxy health + circuit breakers
- `proxy-routing`: per-host + per-tier composable rules; first-match wins; explicit-direct allowed

### Modified Capabilities

- `tier-pipeline`: orchestrator resolves a route per tier, plumbs `proxy_url` into raw/jina, surfaces `proxy` in diagnostics, and now **executes** after-tier `RewriteUrl`/`RetryViaArchive` (with caps) — the PR7b no-op is closed
- `raw-tier`: accepts `proxy_url` kwarg; returns `Verdict.proxy_unavailable` on proxy-layer failure

## Impact

- `pyproject.toml`: no new top-level deps (`purgatory` already present)
- `src/a2web/proxy/__init__.py` + `policy.py` + `pool.py` + `breakers.py`: new package, ~400 LOC total
- `src/a2web/state.py`: `ensure_proxy_pool` helper + atexit, ~30 LOC
- `src/a2web/tiers/raw.py`: `proxy_url` kwarg + curl_cffi plumbing + proxy_unavailable verdict, ~30 LOC delta
- `src/a2web/tiers/jina.py`: `proxy_url` kwarg + httpx plumbing, ~15 LOC delta
- `src/a2web/fetcher.py`: route resolution per tier; after-tier action execution branch; per-fetch caps, ~80 LOC delta
- `src/a2web/models.py`: `Diagnostic.proxy` already exists — populate it; no schema change
- Tests: route resolution table (host/tier composability), proxy pool health transitions, raw tier proxy plumbing, jina tier proxy plumbing, after-tier RewriteUrl execution + cap, after-tier RetryViaArchive execution + cap, proxy_unavailable when required, diagnostic.proxy populated

## Out of Scope (deferred to PR7e)

- **Browser-tier proxy plumbing** — Camoufox `proxy=` launch arg lives at context level, not request level; needs `BrowserPool` rework
- **Archive-tier proxy plumbing** — Wayback rarely needs proxying; archive.ph from TR is the v0.1 motivating case but lower priority than raw/jina
- **Disk-persistent proxy health** at `~/.a2web/proxy-health.json` (1h expiry)
- **Background health-check loop** (every 60s ping `cloudflare.com/cdn-cgi/trace`)
- **CLI commands**: `a2web profile add-proxy`, `add-route`, `show`, `proxy test`
- **Profile system** — v0.1 reuses the global `AppSettings.proxies` + `routes`; multi-profile lands later
- **Global circuit breaker** — 50% of last 100 fetches alarm; hook present, no alerting wired
