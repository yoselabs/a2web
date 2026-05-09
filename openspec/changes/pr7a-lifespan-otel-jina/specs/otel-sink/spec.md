## ADDED Requirements

### Requirement: OTel sink emits one span per phase boundary

The system SHALL define `otel_sink(recv: MemoryObjectReceiveStream[Event]) -> None` in `src/a2web/events/sinks.py`. The sink SHALL lazy-import `opentelemetry.trace`; if the import fails, the sink SHALL still drain `recv` to completion without blocking the producer. For each `TierEnded` and `StageEnded` event the sink SHALL open a span named `a2web.<step>` and immediately end it, attaching attributes `a2web.step`, `a2web.verdict`, `a2web.dur_ms`, `a2web.t_ms`. `Started` events SHALL be ignored (duration is on the `Ended` event).

#### Scenario: OTel SDK absent → sink is a drain

- **WHEN** `otel_sink` runs in an environment where `opentelemetry` is not installed
- **THEN** every event pushed to `recv` is consumed (the producer never blocks) and no exception escapes the sink

#### Scenario: Span attributes are set

- **WHEN** a `TierEnded(step="raw", verdict=Verdict.ok, dur_ms=75, t_ms=84)` event is published
- **THEN** the recorded span has name `a2web.raw` and attributes `a2web.step="raw"`, `a2web.verdict="ok"`, `a2web.dur_ms=75`, `a2web.t_ms=84`

### Requirement: Router attaches OTel sink alongside MCP sink

The system SHALL update `WebRouter.fetch` to subscribe a second receiver from the per-call `EventBus` and start `otel_sink` under the same task group as `mcp_progress_sink`. Sink attachment SHALL be unconditional (the sink itself decides whether OTel is available).

#### Scenario: Both sinks consume the same bus

- **WHEN** the router runs a fetch that publishes 4 events
- **THEN** `mcp_progress_sink` and `otel_sink` each receive 4 events through their respective subscribers
