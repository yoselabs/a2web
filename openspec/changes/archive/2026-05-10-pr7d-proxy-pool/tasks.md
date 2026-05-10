# Implementation Tasks

## 1. Route policy (pure)

- [ ] 1.1 Create `src/a2web/proxy/__init__.py` + `policy.py`
- [ ] 1.2 Implement `ResolvedRoute` dataclass (`proxy_url`, `proxy_id`, `proxy_required`, `fallback`, `matched_rule_index`)
- [ ] 1.3 Implement `resolve_route(host, tier, settings) -> ResolvedRoute`
- [ ] 1.4 Host-glob matcher (exact + `*.glob`)
- [ ] 1.5 ENV var resolution in `proxy.url` (`${ENV_VAR}` → `os.environ`)
- [ ] 1.6 Tests: exact host, glob host, tier match, AND-composition, explicit-direct, default-direct fallthrough, missing proxy → warning + direct

## 2. Proxy pool + breakers

- [ ] 2.1 Create `src/a2web/proxy/breakers.py` — `make_per_host_breaker`, `make_per_proxy_breaker` over purgatory
- [ ] 2.2 Create `src/a2web/proxy/pool.py` — `ProxyPool` with `acquire(host, tier)`, `report(handle, *, success, ms)`
- [ ] 2.3 Health states: alive | quarantined_until(t) | dead (3 consecutive fails → 10 min)
- [ ] 2.4 Acquire honors fallbacks in order, skips quarantined
- [ ] 2.5 `state.ensure_proxy_pool` lazy helper + atexit close
- [ ] 2.6 Tests: acquire returns first healthy; quarantines after 3 fails; falls back; returns None when all dead + proxy_required

## 3. Raw tier proxy plumbing

- [ ] 3.1 Add `proxy_url: str | None = None` kwarg to `RawTier.fetch`
- [ ] 3.2 Pass to `curl_cffi.requests.get(..., proxies={"http": proxy_url, "https": proxy_url})` when set
- [ ] 3.3 Translate proxy-layer errors (`ProxyError`, connection refused with proxy set) to `Verdict.proxy_unavailable`
- [ ] 3.4 Tests: direct path unchanged; proxy URL forwarded to curl_cffi (mock); proxy refused → proxy_unavailable

## 4. Jina tier proxy plumbing

- [ ] 4.1 Add `proxy_url: str | None = None` to JinaTier internals
- [ ] 4.2 Pass to `httpx.AsyncClient(proxy=proxy_url)` when set
- [ ] 4.3 Tests: direct unchanged; proxy URL plumbed (mock)

## 5. Orchestrator wiring

- [ ] 5.1 Resolve route per tier invocation: `pool.resolve(host, tier_name)`
- [ ] 5.2 Plumb `proxy_url` into raw + jina calls
- [ ] 5.3 Populate `Diagnostic.proxy` from resolved route (id or `"direct"`)
- [ ] 5.4 Add `url_rewrites`, `proxy_swaps` per-fetch counters; `archive_dispatches` already exists
- [ ] 5.5 After-tier action execution: consult `next_action_after_tier(tier_result, url, settings)`
  - [ ] 5.5a `RewriteUrl` → restart tier loop with new URL (cap 1)
  - [ ] 5.5b after-tier `RetryViaArchive` → dispatch archive (cap 1, shared with after-gate)
- [ ] 5.6 OTel route attrs on `TierEnded` (`route.matched_rule`, `route.proxy_id`, `route.fell_back`)
- [ ] 5.7 Tests: route resolution per tier; rewrite cap; after-tier archive dispatch; proxy id in diagnostic; orchestrator handles proxy_unavailable + proxy_required correctly

## 6. Gate

- [ ] 6.1 `make lint` clean
- [ ] 6.2 `make ty` clean
- [ ] 6.3 `make test` green, coverage ≥85%
- [ ] 6.4 Update `CLAUDE.md` (proxy package, route resolution, after-tier execution closes PR7b stub)
- [ ] 6.5 Commit `PR7d: proxy pool + after-tier action execution`
- [ ] 6.6 Archive change via `openspec archive pr7d-proxy-pool`
