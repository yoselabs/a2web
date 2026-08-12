## Why

a2web already knows, at the moment it happens, when a fetch failed, timed out, or produced a thin/degraded result — that's what `OperatorHint`/`HINT_CODES` (ADR-0009) exist for. But today that signal dies with the process: a2web attaches at most one optional sink (OTel, gated on the SDK being installed) and otherwise "never writes to a stream of its own" (`settings.py`). For the common case — someone runs a2web with no OTel collector configured — every failure is seen once, by one caller, and then forgotten. There is no way for the maintainer to learn that a given site, tier, or hint code is failing across many installs, or to accumulate the kind of evidence `eval/corpus.yaml`'s "never lose a case" rule wants, without every operator manually noticing and reporting it.

A self-hosted OTLP ingestion path now exists and has been validated end-to-end (live probe: `POST https://feedback-gateway.shen.iorlas.net/v1/logs` with header `X-Api-Key: <token>` → `200 {"partialSuccess":{}}`, OTel Collector → OpenObserve stream `a2web_feedback`). This proposal wires a2web to it, opt-in, reusing the hint vocabulary and the `_record_uptake` best-effort-telemetry pattern that already exists rather than inventing a new subsystem.

## What Changes

- New opt-in config flag (default **off**) that, when enabled, reports a condensed, structured event to the configured gateway whenever a fetch resolves with an `OperatorHint` at `warning`/`critical` severity.
- Delivery is a best-effort async call made once per fetch from the pipeline's aggregation point, after `operator_hints` is fully assembled — the same shape as the existing `_record_uptake` telemetry (`fetcher/pipeline.py`), not a `logging.Handler` attached to the `a2web` logger. (An earlier draft of this proposal assumed the logger-sink shape; corrected during implementation once it was confirmed `OperatorHint`s are never emitted as log records — see `design.md` D1.)
- Reported events carry hint code, severity, tier/handler context, and a2web version — enough to group and triage — but never raw URL, query text, or page content by default. An explicit "include content" opt-up is a separate, off-by-default setting.
- Delivery failures (network error, gateway down, timeout) never fail or delay the fetch they're reporting on — same try/except-to-`log_warning` discipline `_record_uptake` already has.
- Endpoint and credential are configurable (env var), no shipped default for either — a specific gateway URL is a personal identifier and `tests/architecture/test_no_personal_strings.py` forbids one in the shipping tree, so every deployment that opts in points it at a gateway explicitly. (An earlier draft assumed a working default pointed at the maintainer's gateway; corrected once this architecture test failed against it.)
- No local accumulation step, no export command, no new storage subsystem — reports go straight to the gateway when the flag is on, or nowhere when it's off.

## Capabilities

### New Capabilities
- `feedback-telemetry`: the opt-in mechanism itself — what triggers a report, what a report contains (and never contains), the default-off posture, the endpoint/credential configuration surface, and the non-blocking delivery guarantee.

### Modified Capabilities
- None. (An earlier draft listed `app-logging` as modified — dropped once implementation showed this doesn't touch the logging subsystem at all; it's a new function called from the fetch pipeline, not a new log sink.)

## Impact

- **Code**: `src/a2web/fetcher/pipeline.py` (new `_record_feedback` function alongside `_record_uptake`, new call site in `fetcher/__init__.py`'s `fetch()`, alongside `_record_uptake`), `src/a2web/settings.py` (new config fields: enable flag, endpoint URL, API key, content-opt-up flag).
- **Config surface**: new `A2WEB_FEEDBACK_*` env vars (`ENABLED`, `ENDPOINT`, `API_KEY`, `INCLUDE_CONTENT` — resolved in `design.md`).
- **Dependencies**: none new — `httpx` is already a baseline dependency; the OTLP/HTTP POST is a hand-rolled JSON request over it.
- **External systems**: the maintainer's self-hosted OTel Collector + OpenObserve stack (already deployed and probe-verified) is the default target; this is out of a2web's repo but the endpoint/credential are load-bearing configuration.
- **No breaking changes**: default-off, adds a capability without altering any existing tool signature or response envelope shape.
