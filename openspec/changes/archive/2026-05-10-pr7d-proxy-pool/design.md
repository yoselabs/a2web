## Context

`AppSettings.proxies: dict[str, ProxyEntry]` and `routes: list[RouteRule]` have existed since PR1 but no code reads them. Engineering.md §1 specifies a per-host-and-per-tier route policy with first-match-wins, composable AND, explicit-direct, and `proxy_required` to prevent silent direct fallback. PR7b deferred two playbook actions (`RewriteUrl`, after-tier `RetryViaArchive`) saying PR7c would execute them under the proxy retry layer; PR7c shipped browser instead, so PR7d closes both: proxy plumbing AND the deferred action execution.

## Goals / Non-Goals

**Goals:**
- Pure `RoutePolicy` over `(host, tier)` → `ResolvedRoute`; testable without I/O
- Lazy `ProxyPool` (only initialized when first route resolves to a non-direct proxy)
- Per-host + per-proxy circuit breakers via existing `purgatory` dep
- Raw + jina tier plumbed; raw returns `proxy_unavailable` cleanly when proxy refuses
- After-tier action execution: `RewriteUrl` (cap 1) + `RetryViaArchive` (cap 1) — closes PR7b's stub
- Diagnostic rows carry the resolved `proxy` id

**Non-Goals (PR7d):**
- Browser-tier proxy (context-level; PR7e)
- Archive-tier proxy (PR7e)
- Persistent health JSON, health-check background loop (PR7e)
- CLI for proxy/route management (PR7e+)
- Multi-profile support — single global settings is the v0.1 contract
- Global circuit breaker alarming (hook only)

## Decisions

**Route policy is a pure function over settings, not a stateful object.**
`resolve_route(host, tier, settings) -> ResolvedRoute` is pure: same inputs → same output, no I/O. The `ProxyPool` adds the stateful layer (health, quarantine timestamps, breaker integration). Splitting them keeps the policy unit-testable as a table-driven test and makes mismatch bugs obvious. Alternative: bake everything into `ProxyPool` — rejected; testing routing rules against a stateful pool is ten times the harness for the same coverage.

**First-match-wins; explicit `direct` allowed; default-direct fallback.**
The route table is a list, scanned in order. First matching rule decides. A rule can name `proxy = "direct"` to override an earlier broad rule. If no rule matches, the result is `direct`. This matches the engineering.md spec line-for-line and handles the bootstrap case (zero proxies → everything direct, no surprises).

**`proxy_required = true` fails the tier; default `false` falls through.**
When the resolved route has `proxy_required=True` and the proxy is unhealthy with no usable fallback, the tier returns `Verdict.proxy_unavailable` and the orchestrator stops (does NOT silently retry direct — that defeats the routing intent). When `proxy_required=False`, the orchestrator continues to the next tier. Alternative: always fall through to direct — rejected; quietly violating user routing intent is the kind of thing that produces "why is this scraper getting blocked" tickets six months later.

**purgatory for breakers, in-memory state for health.**
purgatory is already a dep (used per-host in PR1's CircuitBreakerFactory). Per-proxy and per-host-raw breakers wrap purgatory directly. Health state (alive/quarantined/dead) lives on the in-memory `ProxyPool` for v0.1; persistence and disk-loaded health are PR7e. Alternative: persistent SQLite-backed health — rejected; health is by nature volatile and "lose state across restarts" is acceptable for v0.1's "lots of laptop, fewer servers" deployment shape.

**After-tier action execution sits inside the tier loop, not after it.**
The current orchestrator loop runs Phase 2 (tiers) → Phase 3 (extract) → Phase 4 (gate) → Phase 4.2 (browser escalation) → Phase 4.25 (archive escalation). After-tier actions fire **inside** Phase 2 — they react to a single tier's result before the loop advances. `RewriteUrl` rewinds the loop with a new URL (capped at 1, anti-loop). After-tier `RetryViaArchive` is a parallel branch to the after-gate dispatch and shares the same `archive_dispatches` cap (still 1 total per fetch — they are mutually exclusive paths to the same recovery).

**Per-fetch caps are kept as plain ints on the orchestrator stack.**
`url_rewrites`, `archive_dispatches`, `proxy_swaps` — small, local, easy to reason about. PR7b set the precedent. Alternative: a `PlaybookState` dataclass — rejected; over-abstracted for three integers.

**OTel route attrs piggyback on existing `TierEnded`.**
The OTel sink already produces one span per `TierEnded`. Adding `a2web.route.matched_rule` / `a2web.route.proxy_id` / `a2web.route.fell_back` as span attrs is one extra dict assignment per tier. No new event type, no new sink.

## Risks / Trade-offs

- **Health is in-memory only.** A restart loses quarantine state and may briefly hammer a dead proxy until it's re-quarantined. Acceptable for v0.1; persistence is PR7e.
- **Per-tier route resolution per request** (not per fetch) means a fetch that escalates through 3 tiers does 3 route lookups — pure dict scans, sub-millisecond, but worth noting if ever profiled.
- **`proxy_required=True` with all fallbacks dead = hard fail.** That's the intended semantic, but operators who don't read the docs may be surprised. Operator hint `code=proxy_unavailable` includes the rule that matched and the proxies that were tried.
- **No test of the actual SOCKS5 path.** Tests use httpbin or local httpx mocks; we trust curl_cffi's `proxies=` and httpx's `proxy=` to do the right thing. Live-network proxy tests are integration territory.

## Migration Plan

1. Land `proxy/policy.py` (pure resolution) + tests; no orchestrator wiring.
2. Land `proxy/pool.py` + `proxy/breakers.py`; lazy ensure helper in state.
3. Wire `tiers/raw.py` to accept `proxy_url`; orchestrator resolves and passes; `proxy_unavailable` verdict path.
4. Wire `tiers/jina.py` similarly.
5. Wire after-tier action execution; close PR7b's deferred stub.
6. Populate `Diagnostic.proxy` and OTel route attrs.

Rollback: revert commit. Settings model unchanged; cache unaffected.

## Open Questions

- Should `proxy_unavailable` count toward the per-host raw breaker? (Probably no — proxy died, not host. Default to no in PR7d; revisit if metrics show pathological behavior.)
- For `RewriteUrl` after-tier execution — does the rewrite restart the loop from the *first* tier or continue from the *current* tier with the new URL? (Restart from first; rewriting an arxiv pdf to abs makes raw-on-the-abs-page the right next step. Cap=1 prevents loops.)
- Should the route table support a wildcard `tier = "*"` for "any tier"? (Defer; an absent `tier` already means "any" today.)
