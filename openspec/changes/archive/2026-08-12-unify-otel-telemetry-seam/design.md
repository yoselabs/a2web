## Context

See `proposal.md` for motivation. Current state, concretely:

- General telemetry: `events/sinks.py`'s `OtelHandler`, attached to the `a2web`
  logger, built on `opentelemetry.trace.get_tracer("a2web")` — the **stable**,
  top-level trace API. Gated on `opentelemetry` being importable
  (`_manifests/sinks/otel.py`); if present, actually exports wherever ambient
  `OTEL_EXPORTER_OTLP_*` env vars point, which a2web never validates, redacts,
  or even knows about — the one `A2WEB_*`-setting file in the codebase with an
  un-gated escape hatch.
- Feedback: `fetcher/pipeline.py`'s `_record_feedback` (from
  `add-a2web-feedback-channel`, archived) — hand-rolled `httpx.AsyncClient`
  POST of an OTLP/HTTP **logs** JSON payload, gated on explicit
  `A2WEB_FEEDBACK_ENABLED`/`_API_KEY`/`_ENDPOINT`, auth via `X-Api-Key`
  (Traefik/forwardAuth boundary on the deployed gateway, not `Authorization:
  Bearer` — probe-confirmed in the prior change).
- `fastmcp` (pinned `>=3.4,<4`, installed `3.4.4`) ships its own OTel
  integration (`fastmcp/telemetry.py`, `fastmcp/server/telemetry.py`):
  per-MCP-method SERVER spans (`tools/call`, `resources/read`, …) tagged
  `mcp.*`/`fastmcp.*`/`gen_ai.*`, plus auth/session attributes. Read directly
  from source (not docs): zero config surface of its own — no constructor
  kwarg, no settings field, nothing. It calls the bare
  `opentelemetry.trace.get_tracer(...)`, which always resolves through
  whatever the process-global `TracerProvider` is.

## Goals / Non-Goals

**Goals:**
- One shared endpoint/credential config feeding both signal types, with an
  explicit per-use-case override — not three independent configs (a2web
  tracing, a2web feedback, FastMCP).
- Provably compatible with FastMCP's native OTel integration — not "should be
  fine," verified by POC.
- No data-contract change to spans/logs any existing consumer (FastMCP itself,
  a future FastAPI product) already emits — additive only.
- Shaped for extraction into `shelf` — framework-agnostic, not FastMCP-named.

**Non-Goals:**
- Not replacing FastMCP's or FastAPI's own span content or attribute schema.
- Not solving metrics (a third OTel signal) — out of scope until a concrete
  need appears.
- Not implementing the shelf module itself in this change — this document
  captures the resolved architecture and POC evidence; implementation is a
  follow-up change once `shelf` is touched (per `AGENTS.md`'s lazy shelf-loop
  resolution).

## Decisions

### D1 — Two seams (traces / logs), one shared config, not one collapsed mechanism

Traces and logs are different OTel signal APIs with different emission
shapes (span start/end vs. one-shot record); collapsing them into a single
function means one fakes the other's shape. Kept separate:

- **Tracing seam**: `opentelemetry.trace` (stable) — a `bootstrap(config)`
  call, made once at composition-root time, that sets the global
  `TracerProvider` + `OTLPSpanExporter`. Both a2web's own phase spans
  (`events/sinks.py`) and FastMCP's own per-call spans ride this same
  provider automatically — no FastMCP-specific glue needed (see D2).
- **Logs/feedback seam**: stays hand-rolled async `httpx.AsyncClient` POST,
  NOT the OTel SDK's Logs API. Checked directly: `opentelemetry.sdk._logs`
  is underscore-prefixed — OTel's own signal that the Python Logs SDK is
  still unstable/private — and its `OTLPLogExporter` takes a
  `requests.Session` (synchronous), which would need an `asyncio.to_thread`
  bridge to call from a2web's async pipeline, violating the project's
  "never add sync I/O in async paths" rule for zero DX gain over what
  already works, is tested, and is probe-verified against the real gateway.

One shared `OtlpEndpointConfig`-shaped settings surface (base
`A2WEB_OTLP_ENDPOINT`/`_API_KEY`/`_ENABLED`, `A2WEB_FEEDBACK_*` as an
optional override) feeds both — "one seam" means one config resolution
path and one mental model, not one function.

### D2 — FastMCP compatibility: verified by POC, not assumed

**Concern:** would a shelf-owned tracer bootstrap conflict with FastMCP's
"native" OTel integration, or produce different span data than following
FastMCP's own prescribed pattern by hand?

**POC** (`.venv`, real `fastmcp` 3.4.4 + `opentelemetry-sdk`): configured an
`InMemorySpanExporter`-backed `TracerProvider` via `trace.set_tracer_provider()`
— literally the pattern in `fastmcp/telemetry.py`'s own docstring — then ran a
real tool call through an in-process `Client`. Captured spans:

```
tools/call add  [SpanKind.SERVER]
  mcp.method.name: tools/call
  fastmcp.server.name: poc-server
  fastmcp.component.key: tool:add@
  gen_ai.tool.name: add
  mcp.session.id: 6bdb28e4-...
```

Then forced the adversarial case — a second attempt to configure the
provider, simulating "our bootstrap also tries to set it":

```
WARNING:opentelemetry.trace:Overriding of current TracerProvider is not allowed
Current global provider is provider_b (the second attempt)? False
Current global provider is provider_a (the first)? True
provider_a's exporter after the "reconfigure": 4 spans, untouched
```

**Finding:** `opentelemetry.trace.set_tracer_provider()` is a global,
first-wins singleton — a hard SDK constraint, not a FastMCP convention.
There is exactly one hook point in the entire SDK; FastMCP's "native"
pattern and a shelf `bootstrap()` are the same call, so there is no
divergent code path that could produce different span data. Grepped the
full `fastmcp` package for any override surface (constructor kwarg,
settings field): none exists. FastMCP is structurally incapable of using a
different provider than whatever the process configures.

**Consequence for design:** the real risk isn't "conflict," it's
**configuration ordering** — whoever calls `set_tracer_provider()` first
wins; a second caller gets one WARNING log line and is silently ignored
otherwise (not a crash, not corrupted data, just a lost configuration
attempt). `bootstrap()` must therefore: (a) run exactly once, as early as
possible in the composition root, and (b) check
`trace.get_tracer_provider()` before setting — if it's already a
non-default/real provider, log a loud warning naming the collision rather
than silently losing.

### D3 — FastAPI compatibility: verified by POC, zero default instrumentation

**Concern:** would a future FastAPI-based product built on this pattern
collide with some default/opinionated instrumentation FastAPI applies on
its own?

**POC** (ephemeral `uv run --with fastapi --with opentelemetry-instrumentation-fastapi`,
isolated from a2web's own lockfile): a plain FastAPI app, with a
`TracerProvider` globally set but `FastAPIInstrumentor` never invoked,
produced **zero spans** for a real request through the ASGI transport.
Explicitly calling `FastAPIInstrumentor.instrument_app(app)` **before** the
first request produced 3 spans in the `http.*` semconv namespace
(`http.route`, `http.method`, `http.status_code`, …) — a fully separate
package, a fully separate attribute namespace from FastMCP's `mcp.*`/
`fastmcp.*`/`gen_ai.*` and a2web's `a2web.*`.

**Gotcha found and worth documenting for whenever a FastAPI product
happens:** calling `instrument_app()` *after* the app has served its first
request is a silent no-op — Starlette freezes its middleware stack on
first dispatch, and `FastAPIInstrumentor` injects itself via middleware.
This is a FastAPI-specific ordering requirement, orthogonal to whether
FastAPI-native or a shelf bootstrap configured the underlying provider —
identical either way.

**Finding:** FastAPI applies no instrumentation by default; nothing to
conflict with. If a future FastAPI product explicitly opts into
`FastAPIInstrumentor`, its spans compose with FastMCP's and a2web's under
the same shared provider for free, same as D2 — again, because there's
only one provider to share.

### D4 — Shelf-worthiness and naming

Explored and rejected: naming this "FastMCP OTel/feedback reporter."
`fastmcp/telemetry.py` has zero logs-signal support, zero endpoint/auth
config, and is purely a thin ambient-tracer wrapper — there is nothing
FastMCP-specific to adopt or extend for the feedback use case, and naming
the module after FastMCP would misrepresent what it does (works identically
for any process using the OTel SDK, MCP or not).

Resolved: a framework-agnostic module — tentatively `shelf.otel` — with two
independent pieces sharing one config type:
- `bootstrap(config) -> None`: tracing seam, sets the global provider once.
- `build_feedback_reporter(config) -> report(...) | NullReporter`: logs
  seam, async hand-rolled POST, degrades to a no-op cleanly when disabled
  or unconfigured (mirrors `_record_feedback`'s existing early-return
  discipline).

Not implemented yet — this change captures the resolved shape; the shelf
loop (`AGENTS.md`) is resolved lazily on first actual touch of `shelf`,
which is the follow-up implementation change, not this one.

### D5 — Live storage-shape findings (OpenObserve query, 2026-08-12)

Queried the real `a2web_feedback` stream (`total: 8` records, none purged)
via the homelab session that owns the OpenObserve stack — not a code change,
verification of what the archived `add-a2web-feedback-channel` change
actually produced once stored, and what it implies for a shared seam with
more callers.

**OTLP structure does not survive storage.** A stored record is fully
flattened — log attributes (`hint_code`, `tier`, `verdict`), resource
attributes (`service_name`, `service_version`), and scope
(`instrumentation_library_name`) all land as bare top-level columns,
indistinguishable from each other:

```json
{
  "_timestamp": 1786199722785611,
  "body": "REGEX_RETEST anti-bot wall ([url-redacted]). Try again. Also bare [url-redacted]",
  "hint_code": "try_user_browser",
  "instrumentation_library_name": "a2web.feedback",
  "service_name": "a2web-feedback",
  "service_version": "0.7.3",
  "severity": "CRITICAL"
}
```

No `trace_id`/`span_id` columns exist on this path — meaning **the logs
seam and the tracing seam cannot be correlated by trace ID once stored**,
only by proximity in `_timestamp`, even though both would ride the same
`OtlpEndpointConfig`. Schema is a per-record union (unset fields create no
column), so a second caller adding a same-named attribute with a different
meaning silently coexists in the same column — a naming collision risk
that grows with the number of callers sharing the stream, not something
either OpenObserve or the collector will catch.

**`severity` is stored raw, unnormalized, and already inconsistent**
across the 8 real records: `"0"`, `"INFO"`, `"warning"`, `"critical"`,
`"CRITICAL"`. a2web's own payload construction (`hint.severity.upper()`,
`fetcher/pipeline.py`) is consistent, so the drift traces to hand-built
probe records from testing — but nothing in the pipeline enforces
normalization, and OpenObserve does not normalize on ingest. A shared
seam with more callers must not assume a clean, comparable severity axis
exists unless something (an OTTL transform on the collector, or a
convention enforced in the shelf module itself) guarantees it.

**No dedup, no id field.** Two byte-identical probe records were found at
an exactly-round, client-set `_timestamp` (second precision). At-least-once
delivery with no idempotency key means duplicates are an inherent property
of this pipeline, not a bug to chase — a shared seam should not add retry
logic to the feedback POST without also deciding whether duplicates are
acceptable (they currently are, silently).

**Body redaction (D3 of the archived change) is confirmed working** on
exactly one record — `REGEX_RETEST anti-bot wall ([url-redacted]). Try
again. Also bare [url-redacted]`, the fourth in a four-commit convergence
sequence (a masking gap, a paren-eating fix, a domain-matching regression,
then clean). But it has never been exercised by a real widget-delivered
report — every ingest since 2026-08-08 14:35Z is a hand-built probe, not
live traffic. The pre-fix smoke record (`https://example.com/smoke-test-page`,
synthetic, unredacted) is still present as agreed.

**Bodies carry instruction-shaped text.** Hint copy is written as
imperative guidance for an agent (e.g. "You MUST either open it in a real
browser tool…") — legitimate for its original purpose, but anything
downstream that feeds stored bodies to an LLM (a future auto-triage
feature, say) must treat them as untrusted data, not instructions.

**The gateway's stream/pipeline scoping is deliberate, not incidental.**
`a2web_feedback` and the single `logs/feedback` collector pipeline are an
explicit a2web-only scope decision on the homelab side. Reusing this same
stack for a second shelf-module consumer (a different MCP server, a
FastAPI product) is a real change to `apps/public/feedback-gateway`, with
its own OpenSpec change on that repo — not something the shelf module
can assume it can just point a new project's config at.

### D6 — Feedback payload is under-specified; redesign around a real diagnostic report

Live-probed (D5, and the follow-up real-payload capture) with the archived
change's actual code: today's report is thinner than "feedback" implies.
`_record_feedback` uses only `fc.observations[-1]` — the escalation chain
(raw tried, jina tried, browser hit a wall) collapses to its last step —
and never sends `status_code`, `content_type`, `cache_state`, `tier_used`,
or `OperatorHint.fix` (the remediation string, already computed, currently
discarded). There's no field distinguishing what was expected: a `query`
call wanting an extracted answer reads identically to a `fetch_raw` call
wanting bytes, and `requested_url` vs `final_url` (redirects/rewrites) is
invisible.

**Resolved shape** — a report should carry, structurally:
- `operation`: `query` | `fetch_raw` — what was expected.
- `requested_url` / `final_url` (when content is included, D7) —
  distinguishes caller input from what a rewrite/redirect resolved to.
- `ask` (when content is included) — the query text, if any.
- **the full escalation chain**, not just the terminal step: each
  `Observation`'s `source` (tier/handler), `verdict`, `authoritative`,
  `t_ms` — in order. This is the actual "what was tried, what happened at
  each step" a diagnostic report needs; `fc.observations` already holds it,
  nothing new to compute.
- `status_code`, `content_type`, `cache_state`, `tier_used` — terminal
  response shape.
- `hint.code` / `hint.severity` / `hint.message` / `hint.fix` — the fix
  field specifically was already being computed and dropped; costs nothing
  to include.
- `a2web_version`, timestamp — unchanged from today.

**Addendum — explicit expectation-vs-result (raised during implementation
review):** the chain and terminal-context fields above describe what was
*tried*, but not, in one place, what was *expected* versus what actually
came back. Added two more fields:
- `expected`: a short fixed string derived purely from `operation` — "an
  extracted answer from the requested URL" for `query`, "raw page content
  from the requested URL" for `fetch_raw`. No new state; a static mapping.
- `result_status` / `result_confidence`: **not** a second computation —
  `_record_feedback` now takes the already-built `FetchResponse` (the exact
  object `fetch()` returns to its caller, built by `build_response` before
  `_record_feedback` is called) and reports its `status` (`ok`/`failed`/
  `partial`) and `confidence` verbatim. This guarantees the feedback
  report's "result" can never drift from what a2web actually told the
  caller — no risk of `_record_feedback` re-deriving `resolve_verdict`
  differently or missing a status override (e.g. the empty-vs-wall
  promotion in `_phase_empty_promotion`) that `build_response` already
  applied.

Exact wire encoding (OTLP `AnyValue` supports `arrayValue`/`kvlistValue`,
so the chain doesn't have to flatten to a delimited string) is
implementation detail for the follow-up change, not resolved here — but
per D5, whatever shape is chosen will flatten to top-level columns once
stored in OpenObserve regardless, so a nested `arrayValue` is for wire
fidelity, not for a queryable structure on the storage side.

### D7 — Redaction ownership: a2web's flag, not a blanket collector floor

**The actual bug behind the "gap" the homelab session found and fixed
(archived change, D3):** `A2WEB_FEEDBACK_INCLUDE_CONTENT` was never
authoritative over the URL leaving the process — it only gates a separate
`url`/`query` attribute pair. `OperatorHint.message` embeds the URL by
design (an agent-facing hint has to say *which* URL hit a wall), and that
text was never covered by the flag at all, flag on or off. The collector's
OTTL `transform` scrubbing `LogRecord.body` unconditionally was a correct
response to a real hole — but it's a band-aid over a2web's own config
knob not doing what its name says.

**Decision, implemented:** fix the flag at the source —
`A2WEB_FEEDBACK_INCLUDE_CONTENT` is now genuinely authoritative over the
hint message text (`_redact_known_urls`, exact substring replacement of
the fetch's own known URLs, not regex), not only the separate attributes.

**Reversed: the ask to relax the collector's blanket scrub.** Sent to the
gateway operator, and correctly declined — for two independent reasons
neither of which this design had accounted for:

1. **The scrub was never actually blocking the stated need.** The
   collector's attribute-level redaction is name-anchored (`^url$`,
   `^query$`, `^content$`, `^body$`). `requested_url`/`final_url` (D6)
   match none of those patterns and arrive in storage intact and
   unmodified with `INCLUDE_CONTENT=true`, today, with zero gateway
   change. Only `body`'s inline URL is affected — and the operator's
   actual debugging need (reading the failing URL) is served just as
   well, arguably better, by a dedicated field than by parsing it back
   out of prose. The premise that content-on required the scrub to
   relax was wrong; nothing was blocked.
2. **The scrub isn't redundant with the flag even now that the flag
   works, because they protect different things.** a2web's flag is a
   correctness control for one well-behaved caller. The collector's scrub
   is a boundary guarantee on a lane-3 endpoint where "the caller" is
   anyone holding the shared API key, with (per the gateway operator) no
   established delete path — a bad record there is effectively permanent.
   Relaxing it would also directly contradict a live requirement on the
   gateway's own side (`a2web-feedback-ingest` spec: the guarantee holds
   "regardless of what attributes the caller sends") — reversing that
   needs an OpenSpec change plus an ADR on their side, not a config edit
   prompted by a satisfied consumer.

**Resolved guidance:** `body` may still read `[url-redacted]` even with
`INCLUDE_CONTENT=true`, depending on the receiving gateway's own policy —
a2web has no control over that once the report leaves the process, by
design. `requested_url`/`final_url`/`requested_query` (D6, renamed per the
naming defects below) are the fields a consumer should actually read the
URL from; they're the authoritative source, not the narrative text.

**Three concrete defects found against the real payload shape (gateway
operator, live) and fixed:**
- `query` (as an attribute key) is itself name-anchored by the same
  redaction pattern (`^query$`) and would have arrived as `****` even
  though a2web never redacted it locally — dead on arrival. Renamed to
  `requested_query`.
- `severity` (the hint's own severity, as an attribute) silently shadows
  OTLP's standard `severityText` in the gateway's flat storage — both want
  the same column name, and the attribute wins, so `severityText` never
  survives (confirmed live: a stored record showed `"critical"` with no
  trace of `"CRITICAL"` anywhere). Renamed to `feedback_severity`.
- The per-step `chain.<i>` nested `kvlistValue` attributes (D6) were an
  unverified encoding — the gateway operator flagged that this specific
  OpenObserve build has already contradicted its own docs twice on
  unrelated points, and that a per-index attribute key risks minting one
  new column per chain step per record against a stream whose schema is
  already a per-record union with no fixed shape (D5) — a real risk of
  schema explosion, not a hypothetical one. Replaced with a single `chain`
  attribute holding the whole step list as one JSON string — unambiguous
  under any flattening behavior, and consistent with how the stream
  already stores everything else (flat columns, D5).

## Risks / Trade-offs

- **[Risk] Bootstrap ordering** — a second `set_tracer_provider()` caller
  anywhere in-process silently loses (one WARNING log line, easy to miss).
  → **Mitigation**: `bootstrap()` checks-before-sets and logs loudly on
  collision (D2); call it first, at composition-root time, before any
  other module that might touch OTel.
- **[Risk] FastAPI instrumentation timing** — `instrument_app()` after
  first request is a silent no-op (D3), a footgun for a future FastAPI
  product, not something this module can prevent since it doesn't own that
  call site.
  → **Mitigation**: document the ordering requirement wherever a FastAPI
  product adopts the shelf config; not actionable in a2web today (no
  FastAPI dependency exists in this repo).
- **[Trade-off] Logs seam stays hand-rolled, not SDK-based** — accepted
  in D1: the alternative (OTel Logs SDK) is explicitly marked unstable
  upstream and sync-only, a worse trade than keeping the already-working,
  already-tested, already-probe-verified httpx path.
- **[Risk] Traces and logs are uncorrelatable once stored** (D5) — no
  `trace_id`/`span_id` column exists on the logs path today, so a feedback
  report and the trace of the fetch that triggered it can only be lined up
  by `_timestamp` proximity, never joined precisely.
  → **Mitigation**: if precise correlation ever becomes a real need, thread
  the active span's trace ID into the feedback payload as an explicit
  attribute at emission time — a2web-side change, not a storage fix; not
  worth doing speculatively today.
- **[Risk] Flat storage schema — cross-caller attribute collisions** (D5) —
  every attribute from every signal lands in the same top-level namespace
  with no OTLP-structure provenance; a second shelf-module consumer reusing
  this stream could silently collide on a column name.
  → **Mitigation**: don't reuse this stream across projects without a
  naming convention (e.g. prefix attributes by `service_name`) decided
  before a second consumer exists — tracked as an open question below.
- **[Risk] Unnormalized `severity`, no dedup** (D5) — confirmed via live
  data, not theoretical: five different literal spellings of severity
  exist in 8 records, and duplicate records with identical content exist
  with no id to dedup on.
  → **Mitigation**: none needed on a2web's own emission path (already
  consistent); a shared seam should document this as an inherent property
  of the pipeline rather than assume a caller can rely on clean severity
  filtering or delivery exactly-once semantics.
- **[Risk] Stored bodies are prompt-injection surface for any downstream
  LLM consumer** (D5) — hint copy is written as imperative agent-facing
  text; feeding stored records to a model without treating `body` as data
  would be a real injection vector.
  → **Mitigation**: not an a2web-side fix; a note for whoever eventually
  builds anything that reads this stream back into an LLM.

## Open Questions

- Exact shelf module path/name (`shelf.otel` vs. something else) — resolve
  on first actual shelf touch, per `AGENTS.md`'s lazy-resolution convention;
  doesn't change this design's shape either way.
- Whether `bootstrap()`'s collision check should be a hard failure or a
  warning-and-continue — leaning warning-and-continue (telemetry must never
  break the host app, consistent with every other sink's isolation
  discipline in this codebase) but worth confirming against `shelf`'s own
  conventions once that repo is in scope.
- Whether a second shelf-module consumer reuses the existing
  `feedback-gateway`/`a2web_feedback` stack (needs its own OpenSpec change
  on the homelab side to generalize stream/pipeline scoping and decide an
  attribute-namespacing convention, per D5) or gets its own gateway
  instance — deferred until a second real consumer exists; not a decision
  this change needs to make speculatively.
