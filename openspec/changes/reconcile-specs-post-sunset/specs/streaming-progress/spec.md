## MODIFIED Requirements

### Requirement: Event types

The system SHALL define `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded` as `@dataclass(slots=True)` in `src/a2web/events/types.py`. Each carries `t_ms: int` (offset from fetch start) and `step: str`. End events also carry `dur_ms`, `verdict`, and an `extra` dict. These are typed event payloads: they are passed directly to `await a2web.log.info(PayloadType(...))` on the single process-wide `a2web` logger (there is no registration step and no event bus), and `a2web.log` resolves each instance to a `logging.LogRecord` — message = the type name, payload dict on the record's structured fields — that attached `logging.Handler` sinks (e.g. `OtelHandler` in `src/a2web/events/sinks.py`) consume.

#### Scenario: TierEnded carries verdict and dur_ms

- **WHEN** a `TierEnded` event is constructed
- **THEN** it has `verdict: Verdict`, `dur_ms: int`, and `extra: dict[str, str | int]` fields

## REMOVED Requirements

### Requirement: EventBus

**Reason**: The `EventBus` mechanism (`src/a2web/events/bus.py`, wrapping `anyio.create_memory_object_stream()` with `publish`/`subscribe`) was retired with the `a2kit` sunset (2026-07-22). Events are no longer fanned out through an in-process pub/sub bus; typed payloads emit synchronously through the single `a2web` logger, and sinks attach as `logging.Handler`s via `a2web.log.add_handler(...)` rather than by subscribing to a stream.

**Migration**: The synchronous typed-event mechanism that replaces the bus is specified by `app-composition` → "Typed events are emitted synchronously and cannot disrupt the caller" and by the `app-logging` capability. The surviving event payload types are covered by the "Event types" requirement above.

### Requirement: Orchestrator publishes phase boundaries when bus is supplied

**Reason**: The `bus: EventBus | None` parameter on `fetcher.fetch(...)` and the publish-around-each-phase mechanism were retired with the `EventBus` itself. The orchestrator no longer takes a bus and no longer conditionally publishes; phase-boundary events emit unconditionally via `await a2web.log.info(...)`, forwarded to sinks only when a sink is attached.

**Migration**: Phase-boundary emission now flows through the synchronous logging path — see `app-composition` → "Typed events are emitted synchronously and cannot disrupt the caller" and the `app-logging` capability. The payload types the orchestrator emits remain as specified by "Event types" above.

### Requirement: MCP progress sink

**Reason**: `mcp_progress_sink(ctx, recv)` and the underlying `ctx.event(...)` / `ctx.report_progress(...)` mechanism were retired with the `a2kit` sunset. There is no `ToolContext` DI kwarg and no MCP progress consumer post-sunset; phases never receive `ctx`. The only sink shape that survives is a stdlib `logging.Handler` (e.g. `OtelHandler`), which consumes resolved log records rather than a receive stream.

**Migration**: Event consumption is now handled by `logging.Handler` sinks attached via `a2web.log.add_handler(...)`, as specified by the `app-logging` capability and `app-composition` → "Typed events are emitted synchronously and cannot disrupt the caller". There is no replacement for MCP-wire progress reporting.

### Requirement: Router builds the bus and wires the sink per call

**Reason**: The per-call bus construction and sink wiring, and the `ctx: a2kit.ToolContext` DI kwarg it depended on, were retired with the `a2kit` sunset. Tools are now plain closures over `Components` registered with `@mcp.tool(...)` in `routers.register_web_tools` / `register_cookies_tools`; their parameter list IS the wire schema (there is no DI-injected, wire-hidden `ctx`), so no per-call bus or sink wiring occurs at the tool boundary. Sinks are attached process-wide via `a2web.log.add_handler(...)` at server build time, not rebuilt per fetch.

**Migration**: Sink attachment now happens once, process-wide, via `a2web.log.add_handler(...)` — see the `app-logging` capability and `app-composition` → "Typed events are emitted synchronously and cannot disrupt the caller". The tool-registration contract (plain closures over `Components`, no DI `ctx`) is specified by `app-composition`.
