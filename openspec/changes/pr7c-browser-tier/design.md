## Context

The cascade has three working tiers (raw / jina / archive) plus site handlers, but no answer for sites that require JS execution. The spike-2026-05-07 ground-truth shows ~3/10 "failed v0.1" URLs are JS-gated (Anubis, Turnstile, JS-only SPAs) and neither jina nor archive recovers them. Camoufox is the only browser engine in v0.1 per engineering.md §2 — patched-Firefox stealth, 0% detection in modern fingerprint suites vs. ~30–60% for vanilla Playwright + stealth on Chrome.

PR7c adds the browser tier, the gate→tier signal that triggers it, and the orchestrator wiring to dispatch it out-of-band. Proxy pool / circuit breakers stay out of scope (next PR — they need the full tier set in place first).

## Goals / Non-Goals

**Goals:**
- Camoufox-only browser tier; lazy-launched; pool-managed; never default
- Gate emits `suggested_tier` so the orchestrator can smart-skip intermediate tiers (anubis at tier 1 → browser directly)
- Graceful degradation when Camoufox/playwright not installed (returns `connection_error` + operator hint, no crash)
- Browser-rendered results cache normally (unlike archive); they're the live page

**Non-Goals:**
- Vanilla Playwright (Chrome) — not shipped in v0.1; Camoufox-only per engineering.md §2
- Patchright / playwright-stealth — patches a worse base less effectively than Camoufox
- Browserless / remote CDP — v0.3
- Anubis PoW solver, Turnstile auto-solve — Camoufox + realistic timing handles most; in-page solvers are v0.2
- Cookie consent dismissal filter list — v0.2
- Proxy routing per-tier — next PR (PR7d)

## Decisions

**Lazy pool with atexit cleanup, mirroring PR7a's sqlite pattern.**
a2kit v0.23 still has no lifespan hook to forward FastMCP's `lifespan=`. The `ensure_browser_pool(state)` helper opens the pool under an `asyncio.Lock` on first invocation; the `_close_browser_pool` atexit hook runs on a fresh event loop (`asyncio.new_event_loop().run_until_complete(...)`) at process exit. Alternative: eager init in `register_state` — rejected; would launch Camoufox on every CLI invocation including ones that never reach the browser tier.

**Browser tier not in TIER_ORDER; dispatched by gate signal, capped at 1 per fetch.**
Same out-of-band pattern as archive (PR7b). Reading `TIER_ORDER` should always reflect *what runs by default*. The orchestrator consults `gate_result.suggested_tier` and (a) advances the cascade pointer to skip intermediate tiers, (b) dispatches the browser tier directly. Cap = 1 browser dispatch per fetch — if browser also returns a block verdict, the cascade is exhausted and we return `failed`.

**`suggested_tier` lives on `GateResult`, not `Verdict`.**
Verdicts are a closed enum used in many places (cache keys, narrative strings, NDJSON log). Adding `suggested_tier` to the verdict would balloon the enum. `GateResult` is the orchestrator-internal struct already; adding `suggested_tier: str | None` is non-breaking. Wire-format remains stable.

**Camoufox/playwright as optional dep group.**
The `[browser]` extras keep the default install lean (~20MB) and let CI/users opt in. Runtime check: `try: from camoufox.async_api import AsyncCamoufox` inside `BrowserTier.fetch`; on `ImportError`, return `Verdict.connection_error` with `operator_hints[code=browser_unavailable, fix="pip install a2web[browser] && playwright install firefox && camoufox fetch"]`. Never crash the orchestrator.

**Persistent contexts keyed by host; page recycling 1:1 per fetch.**
Per-host context keeps cookie jar warm across same-host fetches (cheap path for sites that gate first request only). Page-per-fetch (closed after) avoids cross-fetch state leak. Pool size cap 4 (configurable); LRU eviction on overflow; idle contexts evicted at 300s. Alternative: one global context, reuse pages — rejected; cookie cross-contamination across hosts would cause auth/consent leaks.

**Resource budget per page: 30s wall-clock, 50MB transferred.**
Page closed and tier returns `Verdict.timeout` if exceeded. Not retried (browser fetches are 100× more expensive than raw — retry storms would cook the laptop). Counters surface as `tier_extras["browser_wall_ms"]`, `tier_extras["browser_bytes"]`.

**Smart-skip on `suggested_tier`, not full tier-table reorder.**
When gate at tier N returns `suggested_tier == "browser"`, orchestrator (a) advances past intermediate tiers in `TIER_ORDER`, (b) dispatches browser. Intermediate tiers are *not* invoked. This is the engineering.md §2 "anti_bot.suggested_tier — who decides" contract: detector is local; orchestrator is the only place that maps signal → cascade decision.

## Risks / Trade-offs

- **Cold-start cost (2–4s)** → only paid when gate triggers; most fetches never invoke browser. Lazy + pool amortizes warm fetches to 1–3s.
- **Camoufox binary size + install friction** → optional dep group; clear operator hint when missing; CI installs in gate workflow.
- **Pool exhaustion under fanout** → max_pool=4 with LRU eviction. If 5+ concurrent browser-tier fetches, the 5th waits. v0.2 may add concurrency limit per host.
- **Detection regressions when Camoufox stalls behind upstream Firefox releases** → accept; revisit if benchmarks show >10% degradation.
- **atexit on a fresh loop** can race with running event loops in pytest — bootstrap_state_for_test/teardown_state_for_test must explicitly close the pool to avoid the atexit hook firing on a test loop. Mirrors PR7a sqlite teardown.

## Migration Plan

1. Add `[browser]` optional deps; CI installs and runs browser-tier integration tests behind `@pytest.mark.browser`.
2. Land `gate/block_detector.py` `suggested_tier` field with the signal table; orchestrator reads it but doesn't dispatch yet (no-op).
3. Land `browser/pool.py` + `tiers/browser.py`; smoke test against a local Anubis-fixture server.
4. Wire orchestrator dispatch + 1-browser cap; flip the no-op.
5. Live demo: known Anubis-gated URL → browser tier success.

Rollback: revert commit. No persisted state. Optional deps untouched on existing installs.

## Open Questions

- Per-host context isolation by *profile* too? (i.e., key = (profile_hash, host)) — defer until profile-system lands.
- Should browser-tier results always set `tier_extras["js_executed"]=True` for caller visibility? (Probably yes; cheap.)
- Anubis PoW solver and Turnstile auto-solve — defer to v0.2 or PR7d? (Defer; Camoufox + realistic timing already passes most.)
- `A2WEB_BROWSER_DISABLED` env flag for headless servers without GUI deps? (Defer; the optional-dep group already serves this — don't install `[browser]` and the tier short-circuits.)
