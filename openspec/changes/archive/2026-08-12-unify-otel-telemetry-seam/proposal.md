## Why

`add-a2web-feedback-channel` (archived 2026-08-12) shipped `_record_feedback` as a
standalone, hand-rolled OTLP/HTTP-logs POST — separate in every way from a2web's
pre-existing general-telemetry path (`events/sinks.py`'s `OtelHandler`, which rides
the OpenTelemetry SDK's ambient, SDK-presence-gated `TracerProvider`). Two signals,
two config models, two opt-in stories, one of them (general telemetry) opting itself
in by accident of what happens to be `pip install`ed plus whatever ambient
`OTEL_EXPORTER_OTLP_*` env vars are set — inconsistent with every other `A2WEB_*`
setting in `settings.py`, which is explicit-flag-gated by design.

Separately: this reporting mechanism is not a2web-specific in nature — any MCP
server (or FastAPI service) that wants "opt-in telemetry to a self-hosted OTLP
gateway" needs the same auth/endpoint wiring, the same graceful SDK-absent
degrade, the same non-blocking discipline. That is exactly the shape of a shelf
primitive: DEEP (auth/config resolution is fiddly to get right twice), STABLE
(OTLP wire format), WINS (reused across a2web and future MCP/FastAPI projects
without rebuilding the gateway glue each time).

## What Changes

- One shared endpoint/credential config (base `A2WEB_OTLP_*`, with `A2WEB_FEEDBACK_*`
  as an optional per-use-case override) feeds two seams, not three: a tracing seam
  (general telemetry, spans, built on the stable `opentelemetry.trace` API) and a
  feedback seam (logs, hand-rolled async httpx — the OTel Logs SDK was evaluated and
  rejected, see design.md).
- The tracing seam becomes a shelf-owned `bootstrap()` call: configures the process-
  global `TracerProvider` once, explicit-flag-gated like everything else — no more
  ambient-env-var accidental opt-in.
- Verified by POC (design.md) that this bootstrap is compatible with FastMCP's native
  OTel integration by construction (there is exactly one global-provider hook in the
  SDK; FastMCP's own docs prescribe calling it, our module wraps the identical call)
  and does not collide with FastAPI's optional `FastAPIInstrumentor` (fully separate
  package, separate attribute namespace, zero default instrumentation).
- Both the tracing bootstrap and the feedback reporter are designed to live in
  `shelf` as a reusable, framework-agnostic module — a2web is the first consumer,
  not the only one.

## Capabilities

### New Capabilities
- None yet. The shared tracing bootstrap and its shelf extraction stay deferred
  to a follow-up change once `shelf` is actually touched (design.md D4) — no
  requirement-level spec for that piece belongs here until it has a concrete
  home.

### Modified Capabilities
- `feedback-telemetry`: report content gains the escalation chain and terminal
  response context (design.md D6), and the content-inclusion flag becomes
  authoritative over the hint message text, not only the separate url/query
  attributes (design.md D7).

## Impact

- **Code (future work)**: `src/a2web/settings.py` (collapse `A2WEB_FEEDBACK_*` to an
  override of a new `A2WEB_OTLP_*` base), `src/a2web/events/sinks.py` /
  `_manifests/sinks/otel.py` (tracer bootstrap moves off ambient SDK-presence gating),
  `src/a2web/fetcher/pipeline.py` (`_record_feedback` becomes a thin wrapper over the
  shelf reporter once it exists).
- **External**: `shelf` gains a new module (name TBD — `shelf.otel` explored) — cross-
  repo, resolved lazily per `AGENTS.md`'s shelf-adoption convention on first touch.
- **No breaking changes**: this document captures decisions and POC evidence only;
  no code changes shipped from this change yet.
