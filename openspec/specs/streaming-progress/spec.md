# streaming-progress Specification

## Purpose
TBD - created by archiving change pr6-fit-md-streaming. Update Purpose after archive.
## Requirements
### Requirement: EventBus

The system SHALL provide `EventBus` in `src/a2web/events/bus.py` wrapping `anyio.create_memory_object_stream()`. The bus SHALL expose `async publish(event)` and `subscribe()` (returns a cloned receive stream). The orchestrator is the sole producer; sinks (MCP, future OTel) consume independently. Default buffer size SHALL be 128.

#### Scenario: Single publish reaches all subscribers

- **WHEN** two sinks subscribe and the orchestrator publishes one event
- **THEN** both sinks receive the same event payload

#### Scenario: No subscribers do not block publish

- **WHEN** the orchestrator publishes an event with no subscribers attached
- **THEN** the call returns without raising or blocking

### Requirement: Event types

The system SHALL define `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded` as `@dataclass(slots=True)` in `src/a2web/events/types.py`. Each carries `t_ms: int` (offset from fetch start) and `step: str`. End events also carry `dur_ms`, `verdict`, and an `extra` dict.

#### Scenario: TierEnded carries verdict and dur_ms

- **WHEN** a `TierEnded` event is constructed
- **THEN** it has `verdict: Verdict`, `dur_ms: int`, and `extra: dict[str, str | int]` fields

### Requirement: Orchestrator publishes phase boundaries when bus is supplied

`fetcher.fetch(url, *, state, bus: EventBus | None = None)` SHALL publish `TierStarted`/`TierEnded` around each tier invocation and `StageStarted`/`StageEnded` around each non-tier phase (extract, gate, cache_write). When `bus` is `None`, no events are published and the orchestrator's behavior is unchanged from PR5.

#### Scenario: bus=None preserves PR5 behavior

- **WHEN** `fetch(url, state=state)` is called with no bus
- **THEN** the returned `FetchResponse` is byte-identical to a PR5 invocation against the same fixture (modulo new fit_md and tokens fields)

#### Scenario: bus produces events in chronological order

- **WHEN** the orchestrator runs against a fixture with a sink collecting events
- **THEN** the events arrive in chronological order with monotonically non-decreasing `t_ms`, beginning with a `TierStarted` and ending with a `StageEnded(step="cache_write")` (or earlier if the fetch failed)

### Requirement: MCP progress sink

The system SHALL provide `mcp_progress_sink(ctx, recv)` in `src/a2web/events/sinks.py` that consumes events from a receive stream and forwards them as `await ctx.event(name, **payload)` calls. End events SHALL also call `await ctx.report_progress(progress, message)` where `progress` is a numeric estimate per `v0.1-response-format.md` §3 and `message` is a one-line string formatted with `fmt_dur` for any duration.

#### Scenario: One ctx.event per published event

- **WHEN** the orchestrator publishes 4 events into a bus subscribed by `mcp_progress_sink`
- **THEN** the mock `ToolContext` records 4 `ctx.event` calls with the corresponding event class names

#### Scenario: report_progress only on end events

- **WHEN** the orchestrator publishes a mix of Start and End events
- **THEN** the mock `ToolContext` records `ctx.report_progress` calls only for the End events

### Requirement: Router builds the bus and wires the sink per call

`WebRouter.fetch` SHALL declare `ctx: a2kit.ToolContext` as a kwarg (a2kit DI-injected, hidden from wire schema). The router SHALL build an `EventBus` per fetch, attach `mcp_progress_sink(ctx, ...)` as a subscriber, and pass the bus to `fetcher.fetch(url, state=state, bus=bus)`. After the fetch returns, the router SHALL close the bus cleanly.

#### Scenario: ctx kwarg hidden from MCP wire schema

- **WHEN** an MCP client requests the `fetch` tool's input schema
- **THEN** the schema's parameter list contains `url` only and SHALL NOT include `ctx`

#### Scenario: CLI invocation still works without an MCP client

- **WHEN** `a2web web fetch --url=...` runs from the CLI
- **THEN** the command exits 0 and the `StderrToolContext` adapter handles `ctx.event`/`ctx.report_progress` calls (per a2kit's contract) without erroring

