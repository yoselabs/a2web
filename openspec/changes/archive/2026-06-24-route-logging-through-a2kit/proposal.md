## Why

a2web emits operational diagnostics through a second, unconfigured logging channel: bare `structlog.get_logger("a2web…")` loggers in 6 files. Because a2web never calls `structlog.configure()`, these run on structlog defaults — `PrintLoggerFactory` writes to **stdout** (verified empirically), bypassing a2kit's `LogConfig` entirely. The result: log lines appear identically in CLI and MCP modes regardless of any `A2KIT_LOG__*` setting, a resolved-fallback (e.g. `plugin_unavailable name=anthropic`) reads like a failure, and in MCP **stdio** transport these lines are written into the JSON-RPC channel — a latent protocol-corruption hazard. a2kit's managed channel already provides exactly the contract we want (silent in CLI by default, on the wire in MCP, never stdout, with `call_id`/`trace_id` correlation); a2web's logs just need to route through it.

## What Changes

- Retire the unconfigured `structlog` emit channel: remove all 6 `structlog.get_logger("a2web…")` declarations and their ~9 emit sites.
- Route every a2web operational log through the a2kit-managed `a2kit` logger tree:
  - **Async sites** (`handlers/twitter.py`, `llm_eval/runner.py` ×3) → `await a2kit.log.{info,warning,error}("event", **fields)` — identical `(message, **fields)` ergonomics to structlog.
  - **Sync sites** (`_plugin.py` ×3, `fetcher_response.py`, `wobble/_internal.py` — boot/pure-function contexts with no call scope) → emit via the stdlib half on the `a2kit` logger: `logging.getLogger("a2kit").{warning,info}("event", extra={"a2kit_fields": {…}})`, wrapped in a small `a2web/log.py` sync helper.
- Fix log altitude at the provider-selection chain (the concrete first beneficiary): a non-selected unavailable candidate emits at `debug` (file-only, silent by default); a fully-exhausted chain ("no LLM provider available") surfaces as an `OperatorHint` on the response — the existing user-facing "info link" mechanism (same as `cookies_stale`) carrying an actionable message — NOT a log-channel `warning`.
- **Drop `structlog` entirely** as a top-level dependency: remove the import-and-emit usage AND the `structlog` dependency declaration. a2kit's `StderrPrettyHandler` covers pretty output; `bind_contextvars` is unused. No structlog-as-render-handler is retained.
- **Retire the "LDD" terminology** across a2web live code (the `a2kit.ldd` module was removed in a2kit v0.42 / ADR-0027; only the stale *word* lingers in ~20 a2web comments/docstrings, the `_ldd_ambient` helper name, and 8 `CLAUDE.md` lines). The typed-event functionality (events emitted via `a2kit.log`, sinks as `logging.Handler`s) is unchanged — only the branding is scrubbed. Dated `docs/history/A2KIT_FEEDBACK_*` records are left as-is.
- Add an architecture test banning `structlog.get_logger` under `src/a2web/` so the side channel cannot regrow.
- Correct the stale `CLAUDE.md` convention line ("Structured logging via structlog + bind_contextvars") — `bind_contextvars` is used nowhere in a2web; correlation is supplied by a2kit's `_CallScopeFilter`.
- **Out of scope (separate follow-up):** centralizing LLM-provider selection. The `Provider` Protocol + backends already exist, but `extractor.py` and `judge.py` carry hardcoded `AnthropicProvider()` defaults that bypass the auto/claude-code selection path — a real but distinct provider-resolution refactor, not a logging change.
- **Non-breaking** for the MCP tool contract and response envelopes — this changes the logging substrate only.

## Capabilities

### New Capabilities
- `app-logging`: a2web's operational/diagnostic logging contract — single managed channel on the `a2kit` logger governed by `LogConfig` (CLI-quiet default, MCP-wire forwarding, never stdout), the sync-site stdlib-half emit technique, per-altitude severity policy (resolved ⇒ silent, genuine failure ⇒ logged with hint), and the no-rogue-`structlog` architecture invariant.

### Modified Capabilities
<!-- None. The stale request-log (NDJSON fetch logs) and streaming-progress (old EventBus)
     specs are orthogonal to this developer-diagnostic channel and unchanged. -->

## Impact

- **Code**: `src/a2web/_plugin.py`, `src/a2web/fetcher.py`, `src/a2web/fetcher_response.py`, `src/a2web/packages/llm_extract/wobble/_internal.py`, `src/a2web/handlers/twitter.py`, `src/a2web/llm_eval/runner.py`; new `src/a2web/log.py` sync helper; `src/a2web/llm_resource.py` + the `ask` response path (no-provider `OperatorHint`).
- **LDD scrub**: comments/docstrings in `server.py`, `models.py`, `cookie_jar.py`, `routers.py`, `_manifests/sinks/__init__.py`, `fetcher.py`, `tiers/browser.py`, `events/{__init__,types,sinks}.py`, `llm_eval/{events,live_sink,runner}.py`; rename `runner._ldd_ambient`; two test docstrings.
- **Tests**: new `tests/architecture/test_no_rogue_structlog.py`; existing log-assertion tests updated to read records off the `a2kit` logger (autouse `ambient_for_tests_autouse` already in `conftest.py`).
- **Dependencies**: `structlog` removed as a top-level dependency (no render-handler retained); no new top-level deps.
- **Docs**: `CLAUDE.md` convention line corrected; stale "LDD" branding removed from live-code comments.
- **Behavioral**: MCP stdio stdout stream no longer receives log lines; CLI output silent by default; `plugin_unavailable`-style fallback noise gone on the happy path; no-LLM surfaces as an actionable `OperatorHint`.
