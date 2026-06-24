## Context

a2web has two parallel logging systems:

1. **a2kit managed channel** — `await a2kit.log.{info,warning,error,debug}(...)` lands one `LogRecord` on the stdlib `a2kit` logger. a2kit's `_log_bootstrap.configure_logging(LogConfig)` wires that logger's handlers and an MCP-wire forward. Defaults (verified in `a2kit/config.py`): `stderr_sink="none"`, `wire_level="info"`, `enabled=True`. `_CallScopeFilter` stamps `call_id`/`tool_name`/`trace_id`/`elapsed_ms` on every record. Net behavior: silent in CLI by default, streams on the MCP wire under a call scope, stderr only when opted in, never stdout.

2. **a2web structlog channel** — bare `structlog.get_logger("a2web…")` in 6 files (`_plugin.py`, `fetcher.py`, `fetcher_response.py`, `packages/llm_extract/wobble/_internal.py`, `handlers/twitter.py`, `llm_eval/runner.py`), ~9 emit sites. a2web never calls `structlog.configure()`, so these run on structlog defaults: `PrintLoggerFactory` → **stdout** + `ConsoleRenderer` + `TimeStamper`. This channel ignores `LogConfig` and is identical in CLI and MCP modes.

The `plugin_unavailable` line that triggered this work is channel 2 — a resolved-fallback notice printed to stdout at `info`, in every mode, that an operator reads as a failure.

Key facts that shape the design:
- `a2kit.log` is a **freeform** front door: `_resolve()` in `a2kit/packages/log/emission.py` treats a `str` first-positional as the message and `**fields` as the payload — identical ergonomics to `structlog`. Typed LDD payloads are an option, not a requirement.
- `a2kit.log.*` is `async`; its sync half is `logging.getLogger("a2kit").log(level, msg, extra={"a2kit_fields": {...}})`. The async part only adds the MCP-wire forward, which fires solely under an active fastmcp scope.
- `bind_contextvars` is used nowhere in a2web; the CLAUDE.md convention line is stale.

## Goals / Non-Goals

**Goals:**
- One managed logging channel for all a2web operational/diagnostic logs, governed by `LogConfig`.
- Eliminate writes to stdout (MCP stdio JSON-RPC safety).
- CLI quiet by default; genuine failures logged with a hint; resolved-fallbacks silent.
- Prevent the side channel from regrowing (architecture test).

**Non-Goals:**
- Reworking the `request-log` (NDJSON fetch logs) or `streaming-progress` typed-event *functionality* — orthogonal and unchanged (only stale "LDD" naming on those is scrubbed).
- Introducing typed event classes for every diagnostic (freeform string emit is retained).
- Changing the MCP tool contract or response envelopes.
- **Centralizing LLM-provider selection.** The `Provider` Protocol + manifest-registry selection already exist; the hardcoded `AnthropicProvider()` defaults in `extractor.py:90` and `judge.py:122` that bypass the auto/claude-code path are a real but separate provider-resolution refactor, tracked as its own follow-up.

## Decisions

### D1. Route through the `a2kit` logger, not a freshly-configured structlog

Use a2kit's managed channel rather than calling `structlog.configure()` to fix structlog in place.

- **Why**: a2kit already owns the exact contract we want (CLI-quiet default, wire forwarding, stderr opt-in, no stdout, `call_id`/`trace_id` correlation, an `enabled` kill switch). Configuring a second renderer would duplicate that policy and re-create drift risk. One channel = one policy.
- **Alternative considered**: keep structlog as the emit channel but add a `structlog.configure()` site targeting stderr at a quiet level. Rejected — it leaves two channels to keep in sync and doesn't give wire forwarding or a2kit's scope correlation for free.

### D2. Async sites use `await a2kit.log.*`; sync sites use the stdlib half via a helper

Split the ~9 sites by execution context:
- **Async** (`handlers/twitter.py:117`, `llm_eval/runner.py:241,371,395`) → `await a2kit.log.{warning,debug}("event", **fields)`.
- **Sync** (`_plugin.py:125,135,169`, `fetcher_response.py:86`, `wobble/_internal.py:105`) → a new `src/a2web/log.py` exposing thin sync wrappers, e.g. `log_warning("event", **fields)` → `logging.getLogger("a2kit").warning("event", extra={"a2kit_fields": dict(fields)})`.

- **Why**: `a2kit.log.*` is async and these sync sites are boot/registry/pure-function contexts with no event loop and no call scope. The only thing `await` buys is the MCP-wire forward, which is skipped without a scope anyway — so the sync half loses nothing. Emitting on the `a2kit` logger keeps them under the same handlers, levels, and `enabled` switch.
- **Alternative considered**: make `load_surface` / `emit_wobble` / `_project_routing` async to use `await`. Rejected — viral async churn through pure functions and registry boot for zero benefit (no wire at boot).
- **Helper shape**: keep `a2web/log.py` minimal — `log_debug/log_info/log_warning/log_error(event: str, **fields)` mirroring a2kit's `extra={"a2kit_fields": ...}` convention so records are field-shape-identical to the async path.

### D3. Provider-selection altitude

A non-selected unavailable candidate logs at `debug` (the `_plugin.load_surface` per-miss log for the *provider* surface drops to `debug`). An exhausted chain does NOT emit a `warning` on the log channel — it surfaces to the caller as an `OperatorHint` on the response. The existing path already carries this: `llm_resource._ensure()` returns `None` with `unavailable_reason`, and the `ask` response path turns that into an `OperatorHint` (same mechanism as `cookies_stale`). This change makes that hint's message actionable ("set `ANTHROPIC_API_KEY`, or log into Claude Code") and ensures `ask` does not raise solely for the missing provider (`fetch_raw` remains usable). Surfaces where an unavailable plugin is genuine standalone signal (sinks/tiers/handlers) keep `info`/`warning` as appropriate per-surface.

- **Why**: resolved ⇒ silent (no `info` noise); no-provider ⇒ the user-facing `OperatorHint` is the right surface for "operator must act", not a buried log line. A log-channel `warning` would be invisible in CLI-quiet mode and redundant with the hint.
- **Alternative considered**: hard-fail the `ask` call when no LLM resolves. Rejected — `fetch_raw` still returns useful page content, so degrade-with-hint beats fail-closed.

### D4. Architecture invariant

Add `tests/architecture/test_no_rogue_structlog.py` walking `src/a2web/**.py`, asserting zero `structlog.get_logger(` call sites (AST or source scan, matching the existing `tests/architecture/` style). Grandfather nothing — the migration removes all sites in the same change.

### D5. Drop structlog entirely — no render handler

Remove `structlog` as a top-level dependency, not just its emit usage. Gap analysis confirms nothing load-bearing is lost: a2web uses only freeform `("event", **fields)` emit (covered by `a2kit.log`), never `bind_contextvars` (correlation comes from `_CallScopeFilter`), and pretty output is covered by a2kit's `StderrPrettyHandler` (opt-in via `A2KIT_LOG__STDERR_SINK=pretty`).

- **Why**: one channel, one renderer, one dependency fewer. Keeping structlog as a render-only handler (the earlier draft of this decision) re-introduces a second rendering path to maintain for no functional gain now that a2kit ships a stderr pretty handler.
- **Alternative considered**: retain structlog purely as a `ProcessorFormatter`-backed `logging.Handler`. Rejected per the above; can be revisited if a2kit's pretty output proves insufficient.

### D6. Scrub "LDD" terminology

The `a2kit.ldd` module was removed in a2kit v0.42 (ADR-0027); a2web's logging is now plain `a2kit.log`. Remove the lingering "LDD" word from live-code comments/docstrings, rename `llm_eval/runner._ldd_ambient` (e.g. to `_log_ambient`), and update the 8 `CLAUDE.md` references. The typed-event *functionality* (`events/`, sinks, OTel/live handlers) is unchanged — this is a naming-only scrub. Dated `docs/history/A2KIT_FEEDBACK_*` files are left untouched (historical record). Enforced by the spec's case-insensitive `ldd`-token search over `src/a2web/**.py` + `CLAUDE.md`.

- **Why**: the term now points at a retired module and confuses "it's just structured logging" with a bespoke subsystem that no longer exists.

## Risks / Trade-offs

- **Test assertions that scrape stdout/structlog output break** → migrate them to read off the `a2kit` logger; `conftest.py` already provides the autouse `ambient_for_tests` LDD ambient and `a2kit.testing` helpers. Audit log-asserting tests as a task.
- **Sync helper diverges from a2kit's record shape** → mirror `extra={"a2kit_fields": ...}` exactly and add one test asserting a sync-helper record carries fields under `a2kit_fields`, identical to an `await a2kit.log.*` record.
- **Losing a previously-visible boot diagnostic** (someone relied on `plugin_unavailable` on stdout) → the information is preserved at `debug`/`warning` on the managed channel and is more discoverable via `A2KIT_LOG__STDERR_SINK=pretty`; document the env knobs in the task notes.
- **Wire-level noise if a migrated site picks the wrong severity** → default new emits to `debug` unless the site is a genuine warning/error; the altitude requirement in the spec is the guardrail.

## Migration Plan

1. Add `src/a2web/log.py` sync helper + tests.
2. Migrate async sites to `await a2kit.log.*`.
3. Migrate sync sites to the helper; set provider-miss → `debug`, chain-empty → `warning`.
4. Update log-asserting tests to read the `a2kit` logger.
5. Add the architecture test; remove all `structlog.get_logger` declarations.
6. Correct the CLAUDE.md convention line.
7. `make check` (lint + ty + tests, coverage ≥85%).

Rollback: revert the change set; no data/schema/wire migration is involved.

## Open Questions

- Do any sink/tier/handler `plugin_unavailable` lines deserve to *stay* at `info` (operator wants to know a capability silently won't fire), or should they also move to `debug`? (Decide per-surface during implementation; default to `debug` unless there is a clear operator-expectation argument.)
- Exact `OperatorHint.code` for the no-LLM case (e.g. `llm_unavailable`) and message wording — settle against the existing hint catalogue during implementation.

_Resolved:_ `structlog` is dropped entirely (D5, no render handler). The no-provider case is an `OperatorHint`, not a `warning` (D3). Provider-selection centralization is out of scope (separate follow-up).
