## Context

Through PR6 the orchestrator opens & closes a sqlite connection per fetch (PR3 workaround for a2kit-loop-binding). a2kit v0.23 exposes `App.lifespan(...)` which runs inside the same loop as tools — the workaround is no longer needed. Same hook lets us boot the breaker factory and `LogWriter` once.

Event bus has one consumer (MCP progress). For real-traffic dogfooding we need OTel correlation across fetches; spans-per-phase keyed by `trace_id` are the cheapest unit.

The cascade has only `site_handler` + `raw`. PR4 acceptance spec calls for at least one fallback tier; Jina is the lowest-risk cut (single GET, optional bearer key, returns markdown directly).

## Goals / Non-Goals

**Goals:**
- One sqlite connection per process (lifespan-owned), reused across fetches
- OTel sink subscribed to the existing event bus, no orchestrator changes
- Jina tier slots into the cascade with zero special-casing in the orchestrator
- Tests stay green without an a2kit lifespan running (fixture helper)

**Non-Goals:**
- Archive tier, Camoufox, proxy pool — punted to PR7b/c
- OTel exporter configuration / sampling — caller's responsibility, we just emit
- Jina paid-tier features (image, search) — only the reader endpoint
- Switching log writer to lifespan-shared (already lazy-open & lock-serialized; deferring would mean test changes for marginal gain — but we **do** mount it on AppState at boot to make ownership explicit)

## Decisions

**Lazy singleton with `asyncio.Lock` + `atexit` cleanup.**
a2kit v0.23 does NOT expose a lifespan hook (`a2kit.run` builds FastMCP without forwarding `lifespan=`). Rather than fork the runner or bypass `a2kit.run`, we open sqlite *lazily on first fetch* under an `asyncio.Lock` stored on `AppState`, cache the connection on `state.sqlite`, and register an `atexit` handler at `register_state` time that schedules `close()` on a fresh loop. Same effect — one open per process, reuse across fetches — without the framework hook. Alternatives: (a) bypass `a2kit.run` and call `build_mcp_server(app, lifespan=...)` directly — rejected; loses the unified CLI and CLI's per-invocation `asyncio.run` still needs lazy-open; (b) keep per-fetch open — rejected; the whole point of PR7a was killing connection churn for dogfooding.

`LogWriter` and breaker factory remain populated at `register_state` time (no per-fetch concerns; they were never the problem).

**Test bootstrap via `bootstrap_state_for_test()` helper.**
Tests don't run a2kit's lifespan; the helper opens sqlite + writers synchronously (well, via anyio runner) and returns a populated AppState. Existing test fixtures get replaced. Alternative: parametrize tests with a real App + lifespan — rejected; too much ceremony for unit tests.

**OTel sink: lazy import, env-gated, span-per-phase.**
`otel_sink(recv)` does `try: from opentelemetry import trace` once; if missing, becomes a no-op consumer (still drains the stream so producer doesn't block). Each `TierEnded`/`StageEnded` opens & immediately closes a span with attrs `t_ms`, `step`, `verdict`, `dur_ms`. Span name = `a2web.<step>`. Alternative: emit on `Started` and close on `Ended` to get duration spans — rejected for v1; `dur_ms` attr already carries the timing, and matching pairs across an async stream means storing open spans in a dict keyed by step name, which complicates the sink for marginal value.

**Jina tier as a `pre_rendered` producer.**
Reuses the path Reddit/HN handlers carved: `tier_extras["pre_rendered"] = {content_md, ...}`, gate runs on rendered markdown, trafilatura skipped. Bearer header included only if `settings.jina_key` set. Endpoint: `https://r.jina.ai/<url>`. Alternative: post-process Jina output through pruning — rejected; Jina already returns clean markdown, double-pruning hurts.

**Deny-list as a config field, not a tier-internal hardcode.**
`settings.jina_deny_hosts: list[str]` — Jina sees the URL, so anything secret-bearing (auth-walled, intranet) shouldn't be sent. Default empty in v0.1 so dogfood traffic exercises it; populated as we hit cases.

## Risks / Trade-offs

- **lifespan vs test surface** → fixture helper covers it; CI gate will catch any test that constructs `AppState` directly without going through it
- **OTel optional dep drift** → lazy import + best-effort, sink never raises into the bus
- **Jina rate limits on free tier** → unhandled in v1; tier returns whatever status it gets, gate marks `rate_limited`, cascade moves on (no other post-Jina tier yet, so the fetch fails — acceptable until PR7b/c land)
- **Privacy: Jina sees the URL** → deny-list mitigates; documented in CLAUDE.md update

## Migration Plan

1. Add OTel optional dep group; CI installs it.
2. Land lifespan + helper, switch fetcher to `state.sqlite` (assertion if None).
3. Replace `open_sqlite` calls in tests with `bootstrap_state_for_test`.
4. Add `otel_sink`, wire alongside `mcp_progress_sink` in router.
5. Add `JinaTier`, register, extend `TIER_ORDER`.

Rollback: revert commit. Lifespan changes are additive (per-fetch open path can be restored), Jina tier is opt-in via order.

## Open Questions

- Should `JinaTier` honor `Retry-After` headers? (Probably yes in PR7b when we have circuit-breaker sharing.)
- Do we want the OTel sink to attach `trace_id` from `structlog.contextvars` so MCP-progress and OTel share IDs? (Likely yes; defer until we've actually wired structlog contextvars in real traffic — PR7c.)
