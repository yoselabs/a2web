# streaming-progress Specification

## Purpose
TBD - created by archiving change pr6-fit-md-streaming. Update Purpose after archive.
## Requirements
### Requirement: Event types

The system SHALL define `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded` as `@dataclass(slots=True)` in `src/a2web/events/types.py`. Each carries `t_ms: int` (offset from fetch start) and `step: str`. End events also carry `dur_ms`, `verdict`, and an `extra` dict. These are typed event payloads: they are passed directly to `await a2web.log.info(PayloadType(...))` on the single process-wide `a2web` logger (there is no registration step and no event bus), and `a2web.log` resolves each instance to a `logging.LogRecord` — message = the type name, payload dict on the record's structured fields — that attached `logging.Handler` sinks (e.g. `OtelHandler` in `src/a2web/events/sinks.py`) consume.

#### Scenario: TierEnded carries verdict and dur_ms

- **WHEN** a `TierEnded` event is constructed
- **THEN** it has `verdict: Verdict`, `dur_ms: int`, and `extra: dict[str, str | int]` fields

