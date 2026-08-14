## Why

`feedback-telemetry` (shipped via `add-a2web-feedback-channel`, refined via
`unify-otel-telemetry-seam`) reports every fetch that trips a warning/critical
`OperatorHint` or lands at low confidence — a mechanical, a2web-authored
diagnostic: what was tried, what happened, what a2web itself expected vs.
what it got. It is good at the class of failure a2web can detect: walls,
timeouts, degraded tiers, thin content.

It cannot detect the other class: a mechanically clean fetch (`status: ok`,
`confidence: high`) whose content is simply the wrong thing for what the
calling agent actually needed. a2web has no signal for that — only the
agent that asked the question knows whether the answer actually answered
it. The original idea behind this whole feedback effort ("useless or bad by
judgement of model itself") named exactly this case, and it was explicitly
deferred at the time (`add-a2web-feedback-channel`'s design D1/D4) because
solving it means an agent-invoked tool, which runs into a real discoverability
problem: MCP's on-demand tool loading means agents routinely never notice a
tool they haven't already been told to use (community SEP discussion,
modelcontextprotocol/modelcontextprotocol#2369).

That discoverability problem turns out to already have a working precedent
inside a2web: `OperatorHint.fix` routinely names a specific other tool inline
("Call `fetch_raw` on this same URL...") — the nudge rides a response the
agent is already reading, at the moment it's relevant, rather than depending
on a load-time tool description the agent may never attend to. This change
reuses that exact mechanism for a new tool.

## What Changes

- New MCP tool, `report_feedback(url: str, note: str, wanted: str | None = None)` —
  lets the calling agent report its own subjective read on a fetch: what
  bothered it (`note`) and, optionally, what it would have preferred
  (`wanted`). Both free text, deliberately not a closed category — no real
  corpus exists yet to build a taxonomy from, and forcing self-categorization
  risks the same drift already observed on `feedback-telemetry`'s own
  `severity` field once real callers touched it.
- A cheap, bounded nudge — not a tool-description hope — tells the agent the
  tool exists, exactly when it's likely relevant: appended to an
  already-firing warning/critical hint's `fix` text (zero marginal envelope
  cost), or as one new info-severity hint when no hint fired but
  `confidence == low` (bounded cost, only on already-atypical responses).
  `status: ok, confidence: high` stays completely silent — the
  confidently-wrong case gets no nudge and is explicitly not solved by this
  change (see design.md).
- `report_feedback` reports reuse the exact same OTLP transport as
  `feedback-telemetry` (`_record_feedback`'s POST mechanism), distinguished
  by `scope.name`, not a new pipeline. No new correlation ID: `url` +
  timestamp proximity is how a `report_feedback` call lines up with the
  mechanical report a2web already sent for the same fetch — consistent with
  how the gateway operator already reasons about the stream.

## Capabilities

### New Capabilities
- `agent-invoked-feedback`: the `report_feedback` tool itself — its
  signature, when the nudge to use it fires, what it sends, and what it
  deliberately does not attempt (self-judgment reliability, the
  confidently-wrong gap).

### Modified Capabilities
- None yet — this is a design-stage change capturing an explored, agreed
  shape. Whether `feedback-telemetry`'s existing requirements need a
  companion delta (e.g. to note the shared transport) is a task for the
  implementation follow-up, not this document.

## Impact

- **Code (future work)**: a new tool registration (`routers.py`, alongside
  `query`/`fetch_raw`), a nudge-insertion point in `verdict/terminal.py`
  (where hints are finalized) or `fetcher_response.py` (where confidence is
  computed), and a `report_feedback`-specific POST function reusing
  `_record_feedback`'s transport shape.
- **External**: same gateway/stream as `feedback-telemetry` — no new
  infrastructure, per the design decision to reuse the existing OTLP seam
  rather than invent a second one.
- **Explicitly deferred / not solved by this change**: the confidently-wrong
  failure mode (a2web is confident and wrong) has no trigger in this design
  and remains genuinely unsolved — accepted as a known gap, not an oversight.
  Self-judgment reliability (a bare agent complaint being weak evidence
  alone) is named but not mitigated in this change; a behavioral
  cross-check against `uptake.py`-style re-fetch/escalation patterns was
  discussed as a plausible future direction, not designed here.
