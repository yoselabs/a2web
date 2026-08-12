## Context

This design comes out of an extended exploration session (not previously written down anywhere) that worked through several rejected approaches before landing here. Capturing that history because the rejections carry as much information as the decision.

**Where a2web already stood before this change:**
- `OperatorHint`/`HINT_CODES` (`src/a2web/hints.py`) — a closed, validated vocabulary of ~24 codes, each with `severity` (`info`/`warning`/`critical`) and an optional `fix` string. This already fires on every failure (ADR-0009 "never silently miss a URL"). Several `fix` strings already name a specific other tool by name (e.g. "Call `fetch_raw` on this same URL", "Open the URL in a real browser tool") — this is the precedent that answers the tool-discovery problem below.
- `src/a2web/log.py` — one process-wide `a2web` logger, `propagate=False` + `NullHandler` floor (load-bearing for MCP stdio — nothing may leak onto `stdout`). Exactly one optional sink is attached today: OTel, gated on the SDK being installed, via `add_handler()` (`IsolatingHandler` base class, replace-on-rebuild semantics). No sink is attached by default — an OTel-less deployment (the common case) currently persists failures nowhere.
- `src/a2web/uptake.py` + `fetcher/pipeline.py:_record_uptake` — the one existing precedent for measuring rather than asking, AND the precedent this change actually follows (see D1 correction below): a best-effort async function, called once per fetch from `fetcher/__init__.py`'s `fetch()`, right after `_run_pipeline` returns and the fetch context is fully assembled, wrapped in try/except that swallows failures to `log_warning` rather than raising. Never fails the parent fetch.
- **`OperatorHint`s are NOT currently routed through the `a2web` logger.** Verified by grepping every `fc.operator_hints.append(...)` call site (ten of them, across `pipeline.py`, `answer/prompt_call.py`, `verdict/promotions.py`, `verdict/terminal.py`, `retrieval/cookies.py`, `retrieval/tier_walk.py`, `retrieval/escalate/{loop,browser,paid}.py`) — none also calls `a2web_log.warning(...)` or any other logger emission with the hint. Hints live only on `fc.operator_hints` (a plain list on `FetchContext`) until `build_response(fc)` puts them on the wire envelope. This was discovered during implementation and invalidated the original D1 below; corrected in place.
- No correlation/event id exists anywhere in the response envelope (`models.py`) — a gap noted but explicitly **not** closed by this change (see Non-Goals).

**External state as of this design (verified live, not assumed):**
```
 a2web install
       │  OTLP/HTTP POST /v1/logs, header X-Api-Key: <token>
       ▼
 Traefik (lane-3 apikey middleware, forwardAuth)  ← auth boundary lives HERE
       │
       ▼
 OTel Collector, contrib build, gateway pattern
   pipeline: logs/feedback
   receiver:  otlp (http)
   processor: ratelimit
   processor: redaction
   processor: batch
   exporter:  otlphttp → OpenObserve
       │
       ▼
 OpenObserve, self-hosted, stream = a2web_feedback
```
Confirmed via direct probe against `https://feedback-gateway.shen.iorlas.net/v1/logs`:
`X-Api-Key: <token>` → `HTTP/2 200 {"partialSuccess":{}}`. Confirmed both the original token and a subsequent rotation. The homelab-side operator (a separate session, "OpenObserve and OTEL Collector stack") owns and confirmed this stack; a2web's job starts at "send an authenticated OTLP/HTTP POST to this URL."

## Goals / Non-Goals

**Goals:**
- Let a2web report a condensed, structured signal about its own failures to a central place, opt-in, without becoming a second telemetry system layered on top of general OTel instrumentation.
- Reuse existing patterns (`OperatorHint` vocabulary, `_record_uptake`'s best-effort-call-from-the-pipeline shape) rather than building parallel infrastructure.
- Default-off, safe-by-default content (no raw URL/query/page-content unless explicitly opted up).
- Never let a reporting failure affect the fetch it's reporting on.

**Non-Goals:**
- Not building a general-purpose telemetry/observability pipeline for a2web itself — that's a separate, later, explicitly distinct decision (see rejected-approaches below on why these must stay separate).
- Not adding a correlation/event id to the response envelope in this change — real gap, real future work, out of scope here to keep this change small.
- Not solving "the calling agent's own memory of what happened" — this is telemetry to a2web's maintainer, not a mechanism for the calling agent to remember things across its own sessions.
- Not building local accumulation + manual export (rejected below) — reports go straight to the gateway when the flag is on.
- Not treating a raw LLM self-judgment ("this was bad") as ground truth by itself — see reliability caveat below.

## Decisions

### D1 — Report from the pipeline aggregation point, not a log sink, not a new dedicated tool

**Chosen (corrected during implementation):** a new best-effort async function (`_record_feedback`, alongside `_record_uptake` in `fetcher/pipeline.py`), called once per fetch from `fetcher/__init__.py`'s `fetch()`, right after `_run_pipeline` returns (so `fc.operator_hints` is fully assembled and `build_response(fc)` has already run). Not a new MCP tool the calling agent has to discover and invoke, and — despite the original design below — **not a `logging.Handler`, because there is nothing on the `a2web` logger to observe.**

**Original plan, and why it broke:** the first draft of this design proposed a new `IsolatingHandler` subclass attached via `log.add_handler()`, on the theory that it could observe `OperatorHint`-carrying records the same way `OtelHandler` observes `StageEnded` events. Implementation falsified this: none of the ten `fc.operator_hints.append(...)` call sites across the fetcher also log the hint (see Context above). A log-handler-based sink would receive nothing to react to — the premise assumed a wire that doesn't exist. Rather than retrofit `await a2web_log.warning(hint)` onto ten call sites (real cross-cutting surface, and it would duplicate every hint onto two channels for no benefit), the corrected design reports from the one place `fc.operator_hints` is already complete — which turns out to match `_record_uptake`'s shape almost exactly, not `OtelHandler`'s. The "reuse an existing pattern" principle survives; the specific pattern reused changed.

**Why this reframing doesn't reopen problems (1)/(2):** The earlier design space split into two different problems that got conflated at the start of exploration:
1. "a2web should report its own failures" — a2web already *knows* this the instant it happens (it wrote the hint). No discovery problem, no LLM judgment needed, no new tool surface.
2. "the calling agent should be able to report its own usefulness judgment" — this genuinely needs the agent to say something a2web can't observe on its own.

Problem (1) is the one this change solves, because it's the one where a2web is the source of truth and a sink is a strictly sufficient mechanism. Problem (2) — an agent-invoked feedback tool — was explored and explicitly deferred: it requires solving MCP's on-demand tool-loading discovery gap (see rejected approaches), and the value is unproven at this scale. Should problem (2) become worth solving later, `OperatorHint.fix` already has a working precedent for pointing an agent at a named tool from inside a failing envelope (e.g. "Call `fetch_raw` on this same URL") — reuse that mechanism rather than a load-time tool-description note, which real-world MCP deployments (the community SEP discussion at modelcontextprotocol/modelcontextprotocol#2369) found agents routinely never see under on-demand tool loading.

**Rejected: GitHub issue per event.** No aggregation (one flaky site = N issues), hard dependency on a `GITHUB_TOKEN` sitting in the failure path (exactly the path that most needs to not gain new failure modes), and every report becomes public + indexed by default unless manually marked private every time. Wrong primitive for volume this could produce.

**Rejected: local accumulation + manual export.** Considered "store to a local memory/sqlite file, let the operator export/share later." Rejected on the operator's own reasoning during exploration: nobody manually exports; the value is in a central, always-on stream, not a per-install archive nobody drains. Local accumulation without a drain step is a write-only log — this repo's own house rules are explicit about that failure mode (a guard/log with nothing reading it "reads as coverage while providing none").

### D2 — Transport is OTLP/HTTP logs to a self-hosted gateway, kept structurally separate from any future general-telemetry pipeline

**Chosen:** plain OTLP/HTTP POST (logs signal) to a dedicated Collector pipeline (`logs/feedback`) and OpenObserve stream (`a2web_feedback`), distinct from whatever pipeline general application telemetry would use if a2web ever adds that.

**Why OTel Collector as the gateway, not a bespoke ingestion service:** the operator explicitly did not want to hand-build and run a custom ingestion server. The OTel Collector "gateway pattern" is a standard, widely-documented, config-only deployment: `otlp` receiver, `bearertokenauth`/`basicauth` or upstream-gateway auth, `ratelimit` processor, `redaction` processor (regex/attribute-based PII stripping before storage), `batch`, then export. Zero custom code — this is the answer to "can this be done from traffic configuration alone," and it is.

**Why OpenObserve as the backend, not PostHog or GlitchTip (both seriously considered):**
- *PostHog* — rejected. It's a product-analytics platform (funnels, cohorts, session replay, feature flags, A/B experiments) built human-workflow-first (HogQL/Insights UI is the primary interface, SQL is secondary). Self-hosted PostHog is explicitly unsupported by PostHog itself, feature-gated versus cloud, and the stack (ClickHouse + Kafka + Zookeeper + Postgres + Redis + MinIO, 8–16GB RAM realistic minimum, 1.5GB idle before any data arrives) is disproportionate to "occasional structured reports from a low-traffic MCP server." PostHog's "AI Observability" feature was checked and is a different problem (watching an app's own LLM prompt/completion calls), not this.
- *GlitchTip* — considered as the "crash telemetry" half. It's Sentry-API-compatible and lightweight (1–2GB RAM), and its `OperatorHint`-code-as-exception-type mapping is clean. But two mismatches: (a) it has never implemented Sentry's dedicated user-feedback endpoint (open upstream issue since 2021) — exactly the qualitative "narrative/outcome/judgment" half the operator wanted; workable only by abusing the generic event API's `extra`/`contexts` fields instead. (b) Its core value (automatic dedup) is stack-trace-fingerprint-based; a2web has no stack trace, only a hint code, so dedup would require manually supplied fingerprints — doable, but not the free win it first appeared to be.
- *OpenObserve* — chosen. Single ~40MB binary, no required external Postgres/Kafka/ClickHouse in local mode, native SQL query surface (matches the operator's stated preference for machine/agent-queryable data over a human-dashboard-first product), native OTLP ingestion (composes with the Collector gateway with no glue code), and already shows up in the open-source LLM-observability conversation (Langfuse/Helicone peer set) rather than being a stretch fit.

**Why kept structurally separate from general telemetry, not one unified pipeline:** explicit operator requirement — "feedback is one thing... if we really want, we could separately send like open telemetry analytics." Achieved by pipeline naming within one Collector process (`logs/feedback` today; a hypothetical `logs/telemetry` later would be a new named pipeline, new receiver port/path, new stream — never merged into the same stream even if run on the same Collector instance).

**Default-endpoint correction discovered during implementation:** the original plan shipped `feedback_endpoint` defaulting to the maintainer's live gateway URL, so opting in required only the enable flag + key. `tests/architecture/test_no_personal_strings.py` (a pre-existing guard against operator identifiers in `src/a2web/`) failed against this — the gateway URL is a personal domain. Corrected: `feedback_endpoint` defaults to `""` like `feedback_api_key`, and `_record_feedback` no-ops unless both, plus the enable flag, are set. Every deployment that opts in supplies its own endpoint.

**Auth correction discovered during live probing:** original assumption was a `bearertokenauth` extension checked inside the Collector itself (`Authorization: Bearer <token>`). Live probing found this wrong — three isolating probes (token present / absent / to bare host root) all returned an identical `401` with no `WWW-Authenticate` header and an nginx-branded (not Collector-branded) error body, meaning the request was being rejected *before* reaching the Collector at all. The homelab operator confirmed: auth is enforced at the Traefik/forwardAuth boundary via `X-Api-Key: <token>` (their "lane-3" convention — one auth boundary per lane, not duplicated inside the app). **a2web must send `X-Api-Key`, not `Authorization: Bearer`.** This is a load-bearing correction to carry into implementation — the header name is not a free choice.

### D3 — Content scoping: hint fields yes, raw content no (unless explicitly opted up)

**Chosen:** default report payload = hint `code`, `severity`, tier/handler context, a2web version, timestamp. Explicitly excluded by default: raw URL, query text, page content/narrative body. A separate, independently-off-by-default setting can opt a given deployment up to including raw content.

**Why:** ADR-0009's `narrative` field can carry page content; shipping that off-box by default to a third party turns "error tracking" into something with real privacy weight the operator didn't sign up for by just enabling a bool flag. The Collector's `redaction` processor is the enforcement point for this — one choke point instead of trusting every a2web install to scope correctly, matching D2's config-driven-gateway approach.

**Gap found and closed after real payload delivery:** the gateway's `redactionprocessor` only operates on OTLP `attributes`, not on `LogRecord.body` — and a2web's hint `message` (the human-readable narrative, e.g. "Open the URL in a real browser tool... anti-bot wall (https://example.com/page)") lands in `body`, not an attribute. Confirmed live: the first real smoke-test report (§ tasks.md 5.3b) landed on the gateway with its URL plainly visible in the body text, unredacted, regardless of `A2WEB_FEEDBACK_INCLUDE_CONTENT` being off. The homelab operator fixed this gateway-side with an OTTL `transform` processor that regex-scrubs URL-shaped substrings out of `body` unconditionally — true defense-in-depth, independent of what a2web sends in `attributes`. Nothing changed on a2web's side; recorded here because it means the redaction guarantee in this design now genuinely covers "URLs never leak," not only via the attribute path this repo controls. The one pre-fix smoke-test record (a synthetic `example.com/smoke-test-page` URL, not real data) was left as-is rather than purged.

### D4 — Self-judgment is a weak signal; don't treat it as the primary trigger

**Not implemented in this change, recorded for future work:** research surfaced during exploration (LLM self-assessment reliability, self-preference bias literature) found that a model judging its own output as "good"/"bad" without external grounding is unreliable and biased toward its own family's outputs. This change's triggers (hint severity `warning`/`critical`) are externally-grounded — a2web's own pipeline observed a real failure — which sidesteps the self-judgment reliability problem entirely for v1. If a future change adds an agent-invoked "this was unhelpful" tool (problem (2) from D1), it should be correlated against a behavioral signal (e.g. the `uptake.py`-style pattern of re-querying the same URL, or falling back from `query` to `fetch_raw` on the same URL) rather than trusted as sole ground truth.

## Risks / Trade-offs

- **[Risk]** A misconfigured or compromised feedback endpoint could receive more than intended if the redaction processor's rules don't match a future hint field. → **Mitigation:** redaction happens at the Collector (D2/D3), not solely trusted to a2web-side code; still, a2web-side code should not emit fields outside an explicit allow-list, not rely on the gateway alone as defense-in-depth.
- **[Risk]** Shared credential exposure: the `X-Api-Key` token is a single shared secret across all a2web installs that enable the flag, not an individually-revocable per-install credential (unlike a true Sentry DSN model). A leaked token requires a global rotation, not a single-install revoke. → **Mitigation:** accepted for v1 given operator's explicit choice to hardcode a single token; flagged as a known limitation, not solved here. Rotation was exercised once already during probing and is operationally cheap (confirmed live).
- **[Risk]** Delivery failure modes (gateway down, DNS failure, timeout) must not add latency or failure risk to the fetch path. → **Mitigation:** `_record_feedback` follows `_record_uptake`'s try/except-to-`log_warning` shape, not the `IsolatingHandler` mechanism (D1 correction) — the HTTP call is bounded by a short client timeout and any exception is swallowed rather than raised, so it cannot block or fail the response.
- **[Trade-off]** No local accumulation means an operator with the flag off loses the data entirely if they later want it — no retroactive recovery. Accepted: the alternative (local accumulation nobody drains) was rejected as lower-value than a clean binary choice.

## Migration Plan

- Purely additive: new config fields default to off/empty, one new function plus one new call site in `fetcher/__init__.py`'s `fetch()`, no change to existing tool signatures, response envelope, or logging behavior when the flag is unset.
- Rollback: unset the flag (or don't set it) — no data migration, no schema change, nothing to undo.

## Open Questions

- ~~Exact env var names~~ — resolved during implementation: `A2WEB_FEEDBACK_ENABLED`, `A2WEB_FEEDBACK_ENDPOINT`, `A2WEB_FEEDBACK_API_KEY`, `A2WEB_FEEDBACK_INCLUDE_CONTENT`, following the existing `A2WEB_*`/`AppSettings` field-naming convention.
- ~~Hand-rolled POST vs. OTel SDK/exporter dependency~~ — resolved: `httpx` is already a baseline dependency (`pyproject.toml`), so the HTTP POST is hand-rolled JSON over `httpx`, no new dependency, no "ask first" needed.
- Exact mapping from `OperatorHint` fields to the OTLP log record's attributes (which fields are tags vs. body vs. resource attributes) — implementation-level detail, nailed down in `tasks.md` §2.
- Whether a2web version should come from package metadata (`importlib.metadata.version("a2web")`) or a build-time constant — check existing convention in the codebase before implementing; still open.
