## REMOVED Requirements

### Requirement: EventBus

**Reason:** Replaced by a2kit v0.26's built-in emission chain (`a2kit.ldd.event` / `a2kit.ldd.report` free functions) plus subscriber sinks via `app.ldd.add_sink(...)`. The internal anyio MemoryObjectStream fan-out is no longer needed.

**Migration:** Delete `src/a2web/events/bus.py`. The orchestrator emits directly via `a2kit.ldd.event(ctx, name, **payload)`. Subscribers (OTel exporter) are registered via `app.ldd.add_sink(otel_sink)` in `server.py`.

### Requirement: MCP progress sink

**Reason:** a2kit v0.26 owns the bridge between ldd emissions and the FastMCP wire (ctx.event + ctx.report_progress). The custom `mcp_progress_sink` in `src/a2web/events/sinks.py` is no longer needed.

**Migration:** Delete `mcp_progress_sink` and the `_ProgressCtx` Protocol. The `WebRouter.fetch` method drops the anyio task group + bus wiring; it now reads as:

```python
@a2kit.read(Surface.ALL, idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(self, *, url: Annotated[str, a2kit.Param(...)], state: AppState, ctx: a2kit.ToolContext) -> FetchResponse:
    """..."""
    return await orchestrate(url, state=state, ctx=ctx)
```

### Requirement: Router builds the bus and wires the sink per call

**Reason:** Same as above — the router no longer manages an internal bus.

**Migration:** Implicit in the new `WebRouter.fetch` body shown above.

## MODIFIED Requirements

### Requirement: Event types

The system SHALL define `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, and `TierHeartbeat` as `@dataclass(slots=True)` (or pydantic models per a2kit's typed-event registry contract) in `src/a2web/events/types.py`. Each carries `t_ms: int` (offset from fetch start) and `step: str`. End events carry `dur_ms: int`, `verdict: Verdict`, and `extra: dict[str, str | int]`. `TierHeartbeat` carries `elapsed_in_tier_ms: int`, `step: str`, and an optional `detail: dict[str, str]` (e.g., browser-current-url, archive-current-upstream).

The types SHALL be registered on `app.ldd.events` so a2kit can route them through the typed-emit path (one call emits the dump + event + progress).

#### Scenario: Typed registry registration

- **WHEN** `from a2web.server import app` is imported
- **THEN** `app.ldd.events` carries registrations for `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, and `TierHeartbeat`

#### Scenario: TierHeartbeat carries elapsed-in-tier

- **WHEN** a `TierHeartbeat` is constructed
- **THEN** it has `elapsed_in_tier_ms: int`, `step: str`, and an optional `detail: dict[str, str]` field

### Requirement: Orchestrator publishes phase boundaries via a2kit

`fetcher.fetch(url, *, state, ctx)` SHALL emit `TierStarted` / `TierEnded` around each tier invocation and `StageStarted` / `StageEnded` around each non-tier phase (extract, gate, escalate-browser, escalate-archive, fit, cache-write). Emissions SHALL go through `a2kit.ldd.event(ctx, ...)` (or `app.ldd.events.emit_typed(ctx, evt)` when typed emit is preferred). The orchestrator SHALL NOT carry a `bus` parameter; ctx is the sole emission target.

#### Scenario: Phase boundary emissions reach subscribers

- **WHEN** the orchestrator runs against a fixture with a custom sink registered via `app.ldd.add_sink(...)`
- **THEN** the sink receives `TierStarted` / `TierEnded` for each tier and `StageStarted` / `StageEnded` for each phase, in chronological order with monotonically non-decreasing `t_ms`

#### Scenario: No bus parameter on fetch

- **WHEN** static analysis walks `a2web.fetcher`
- **THEN** the public `fetch(url, *, state, ctx)` signature has exactly three named parameters and no `bus: EventBus | None` parameter

## ADDED Requirements

### Requirement: TierHeartbeat emissions from slow tiers

The browser tier SHALL emit a `TierHeartbeat` event every 2s while a page-load is in flight, carrying the current page URL (if available) in `detail`. The archive tier SHALL emit a `TierHeartbeat` per hedged-request boundary (Wayback completion, archive.ph completion), carrying the current upstream identity in `detail`. Heartbeats SHALL stop when the tier returns. Cancellation SHALL terminate heartbeat emission cleanly.

#### Scenario: Browser tier emits heartbeats during page load

- **WHEN** the browser tier loads a page that takes 6 seconds
- **THEN** at least two `TierHeartbeat` events are emitted with `step="browser"`, `elapsed_in_tier_ms` monotonically increasing, and one final `TierEnded` event after the heartbeats

#### Scenario: Heartbeat stops when tier returns

- **WHEN** the tier completes (any verdict)
- **THEN** no further `TierHeartbeat` events are emitted for that tier instance

#### Scenario: Heartbeat budget kill-switch

- **WHEN** `app.set_ldd(events=False)` is in effect
- **THEN** no `TierHeartbeat` events reach any sink (typed-validate still runs to keep tests deterministic)

### Requirement: OTel sink registered on app.ldd

The system SHALL provide `otel_sink` in `src/a2web/events/sinks.py` (≤ 25 LOC) as an async callable matching a2kit's `Sink` protocol. The sink SHALL emit one OTel span per `*Ended` event (lazy-importing `opentelemetry.trace`); when the OTel SDK is absent, the sink SHALL drain emissions silently. Registration SHALL happen in `server.py` via `app.ldd.add_sink(otel_sink)`.

#### Scenario: Span emission when OTel SDK present

- **WHEN** a fetch completes and `opentelemetry-sdk` is installed
- **THEN** one OTel span is created per `TierEnded` / `StageEnded` event with attributes `a2web.step`, `a2web.verdict`, `a2web.dur_ms`, `a2web.t_ms`

#### Scenario: Graceful degrade when OTel absent

- **WHEN** `opentelemetry` is not importable
- **THEN** `otel_sink` consumes every emission without raising and produces no spans
