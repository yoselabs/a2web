# Tasks — a2kit v0.41 → v0.43 migration

Step ordering is load-bearing. See `design.md` "Migration order".

---

## Step 0 — Pin bump + red baseline

- [x] 0a. **Sanity re-grep architecture fitness functions** — already audited in
  exploration: no `tests/architecture/` test asserts MCP tool-name shape (design.md
  "Unknowns resolved"). Just re-grep `tests/architecture/` post-edit to confirm no
  new name assertion crept in. Not a blocker.
- [x] 0b. **Bump pin** — `pyproject.toml`: spec `a2kit>=0.41,<1` → `a2kit>=0.43,<1`;
  `[tool.uv.sources] a2kit.tag` `v0.41.1` → `v0.43.0`.
- [x] 0c. `uv sync --all-extras`. Confirm install clean.
- [x] 0d. **Red baseline** — `make check`. Expect red: import errors from
  `a2kit.ldd`, `a2kit.packages.ldd`, `App(...)`/`add_router`. Capture the failure
  surface before editing.

## Step 1 — Front A: App composition (ADR-0028)

- [x] 1a. `server.py`: replace `app = a2kit.App("a2web")` + `add_router(...)` with
  `class A2Web(a2kit.App): name = "a2web"; routers = (WebRouter, CookiesRouter)`.
  Keep `build_app()` returning an `A2Web()` instance with the seven `.provide()`
  calls verbatim.
- [x] 1b. `server.py`: delete the `for _event_type in (...): app.ldd.events.register(...)`
  loop (no pre-registration in the refound model). (LDD sink wiring handled in Step 2.)
- [x] 1c. `routers.py`: drop `tools: ClassVar[...]` from `WebRouter` and
  `CookiesRouter` (verbs auto-collect). Drop the now-unused `Callable`/`ClassVar`
  imports.
- [x] 1d. `tests/capabilities/app_state/test_app_state.py`: `a2kit.App("test-probe")`
  + `add_router(WebRouter())` → `a2kit.testing.app_of("test-probe", WebRouter)`.
- [x] 1e. Grep for any other `a2kit.App(` / `add_router` / `tools =` /
  `app.ldd.events` callsite; migrate.

## Step 2 — Front B: LDD → stdlib logging (ADR-0027)

- [x] 2a. **Emit sites** — replace all 28 `await a2kit.ldd.event(X)` with
  `await a2kit.log.info(X)`. **KEEP the `await`** — `info` is `async def`
  (awaits the optional MCP-wire forward; verified in `a2kit/packages/log/
  emission.py:100`). Files: `fetcher.py`, `tiers/browser.py`,
  `llm_eval/runner.py`. Swap `import a2kit.ldd` → `import a2kit.log` (or
  `from a2kit.log import info`).
- [x] 2b. **OtelHandler** — `events/sinks.py`: rewrite `otel_sink(emission)` as
  `OtelHandler(logging.Handler)` with sync `emit(record)` reading
  `record.getMessage()` + `record.a2kit_fields` (design.md D-OtelHandler).
- [x] 2c. **Sink manifest** — `_manifests/sinks/__init__.py`: `Sink` type
  `a2kit.packages.ldd.LddSink` → `logging.Handler`; manifest returns a handler
  instance. `otel.py` manifest builds `OtelHandler()`.
- [x] 2d. **Boot wiring** — `server.py`: `app.ldd.add_sink(...)` →
  `app.log.add_handler(h)` over the `load_surface(...)` handlers.
- [x] 2e. **events module** — `events/__init__.py` + `events/types.py`: update
  docstrings (no more `a2kit.ldd`/`LddEmission` framing); confirm typed payloads
  are unchanged (they pass straight to `a2kit.log.info`).
- [x] 2f. **LiveSink rework** (decided — see design.md D-LiveSink) —
  `llm_eval/live_sink.py`: `LiveSink(logging.Handler)`; `__init__` calls
  `super().__init__()`. `emit(self, record)` sync: `record.getMessage()` +
  `getattr(record, "a2kit_fields", {})` → sync `_on_started`/`_on_ended` (drop
  all `async`/`await`). **Delete the `asyncio.Lock`** — counter mutation in
  `emit` is already under the handler's built-in `self.lock` (logging wraps
  `emit`); the heartbeat reads counters under `with self.lock:`. Retain the
  async `__aenter__/__aexit__` heartbeat task. No fallback needed.
- [x] 2g. **`_ldd_ambient` collapse** — `llm_eval/runner.py`: replace the
  `ldd_state_for_call(...)` body with
  `logging.getLogger("a2kit").addHandler(h)` / `.removeHandler(h)` over the
  bench handlers (confirmed target — `app.log.add_handler` ≡ this; design.md
  D-Ambient). Rename the `sinks=` param to `handlers=`. Drop `from
  a2kit.packages.ldd import LddSink`, `from a2kit.ldd import ldd_state_for_call`,
  `import a2kit.ldd`, and the `null_context` import (scope no longer needed).
- [x] 2h. **Type-ref sweep** — replace remaining `from a2kit import LddEmission`
  (`events/sinks.py` TYPE_CHECKING, `llm_eval/live_sink.py`) and `LddSink`
  references with `logging.LogRecord` / `logging.Handler`.

## Step 3 — Front C: tool-name pins

- [x] 3a. `routers.py`: add `canonical_name_override="ask"` / `"fetch_raw"` to the
  two `WebRouter` verbs and `"refresh"` to the `CookiesRouter` verb.
- [x] 3b. **Verify wire names** (confirmed reachable — design.md "Unknowns
  resolved"). Add a regression test driving the in-process client over
  `build_app()`. Exact assertion: list the client's tool catalog and assert
  `{"ask", "fetch_raw", "refresh"} <= names` AND
  `names.isdisjoint({"web_ask", "web_fetch_raw", "cookies_refresh"})`.
  Satisfies the two scenarios in `specs/app-composition/spec.md` (bare names
  present, flat names absent). `make_client` drives the production
  `build_mcp_server`, so the override is reflected — this test passes once 3a
  lands.

## Step 4 — Tests touched by the LDD rework

- [x] 4a. `tests/capabilities/request_log/test_otel_sink.py` — synthetic
  `LddEmission` fixtures → synthetic `logging.LogRecord` (set `.a2kit_fields`);
  drive `OtelHandler().emit(record)`.
- [x] 4b. `tests/capabilities/output_benchmark/test_live_sink.py` — fake-sink
  shape (`__call__(emission)`) → `logging.Handler.emit(record)`; update the
  `from a2kit import LddEmission` import.
- [x] 4c. `tests/capabilities/tier_pipeline/test_fetcher.py` — any `a2kit.ldd`
  reference; migrate.

## Step 5 — Front D/E + close-out

- [x] 5a. **Lint codes** — grep `# noqa: A2K` across repo; expected none, verify.
- [x] 5b. **CLAUDE.md rewrite** — full pass to the v0.43 surface: subclass App
  composition, `routers=` ClassVar, dropped `tools=`, `a2kit.log` (not
  `a2kit.ldd`), `app.log.add_handler`, flat-name + override note, no
  `app.ldd.events.register`. Update the "Architecture (a2kit v0.39 mediated)"
  header and the per-module prose.
- [x] 5c. `make check` green (lint + ty + test, coverage ≥85%).
- [x] 5d. **`make install-global`** — rebuild the global binary so Claude Code
  picks up the new code (names unchanged; binary must rebuild).
- [ ] 5e. Optional: `make bench` if anything in the extract/envelope path moved
  (it shouldn't here — pure framework migration; skip unless 2f/2g shifted bench
  output). DEFERRED — live-network + spends LLM quota; 2f/2g only changed console
  rendering + event delivery, not scoring. Run manually if you want to eyeball
  the LiveSink console renderer.
- [x] 5f. Update `CHANGELOG.md` + `docs/history/` feedback round if warranted.
