# Design — a2kit v0.41 → v0.43 migration

## Surface verification (done during exploration)

Confirmed against the local `~/Workspaces/a2kit` checkout at `v0.43.0`:

- `app.log` exists (`App.__init__` sets `self.log = _AppLog()`); `app.log.add_handler(handler: logging.Handler)` at `a2kit/packages/log/app_log.py:21`.
- `a2kit.log.info/warning/error/debug(__msg, /, **fields)` — **async** (`async def info(...): await _emit(...)`). `_emit` first does a **synchronous** `_LOGGER.log(levelno, msg, extra={"a2kit_fields": resolved})` to `logging.getLogger("a2kit")`, then awaits an optional MCP-wire forward (`await scope.ctx.log(...)`) when a dispatch scope is present — outside a dispatch (e.g. the bench) `scope` is None and it returns early. **Every emit site keeps `await`.** For a typed instance: `msg = type(instance).__name__` (→ `record.getMessage()`), payload = `model_dump`/`asdict` → `record.a2kit_fields` (`a2kit/packages/log/emission.py`). The handler half — `_LOGGER.log` → `Handler.handle` → `Handler.emit` — is fully **synchronous** and runs inline on the caller's thread, so `logging.Handler.emit(record)` is the correct sink shape regardless of `info` being async.
- `bind_call_scope` lives at `a2kit.packages.log.scope` (replaces `ldd_state_for_call`).
- `null_context` survives at `a2kit.packages.testing.null_context`.
- `a2kit.testing.{app_of, ambient_for_tests, lazy, peek, resolve, client}` all survive.
- `.provide()` is **not** in the v0.43 tombstone table — instance `app.provide(T, f)` still works (only `register`/`resolve`/`add_router` were removed). So `build_app()` keeps its seven `.provide()` calls verbatim under the new subclass.
- Repo grep: **no** `expose=`/`visibility=`, **no** `# noqa: A2K*`, **no** `A2KIT_LDD__*` env. The only LDD-config callsite in the whole repo is `runner.py:64` (`ldd_state_for_call(...)`).

## D-Names — preserve bare tool names (Front C decision)

**Decision:** keep both routers, pin each verb with `canonical_name_override`.

```
                         MCP wire        CLI            grouping
current (v0.41)          ask             a2web web ask  web / cookies
v0.42 default (flat)     web_ask         a2web web ask  web / cookies     ← MCP name changes
(b) override (CHOSEN)    ask             a2web web ask  web / cookies     ← both preserved
drop router (rejected)   ask             a2web ask      flattened         ← CLI changes, grouping lost
```

The "drop the router and use App-level bare verbs" alternative *would* preserve
the MCP name for free, but it flattens the CLI from `a2web web ask` to
`a2web ask` and conflates two distinct domains (web fetching vs cookie refresh)
as bare App verbs. The override costs three one-word kwargs and preserves every
surface. a2web is solo-consumed and the bare names are already wired into the
operator's own Claude Code MCP config — preserving them avoids a re-learn + a
silent contract break.

Pin sites (`routers.py`): `ask` → `canonical_name_override="ask"`, `fetch_raw`
→ `"fetch_raw"`, `refresh` → `"refresh"`.

## D-LiveSink — DECIDED (cleaner than first thought; no fallback needed)

`LiveSink` today is an **async callable** sink: `async def __call__(emission)`,
`asyncio.Lock` around counter mutation + console writes, an `asyncio.create_task`
30s heartbeat spawned in `__aenter__` (full source read: `llm_eval/live_sink.py`).

**Concurrency reality (read from `llm_eval/runner.py`):** bench cells run as
`asyncio.create_task` + `asyncio.gather` on **one event loop, single-threaded**
(bounded 4-way). Emits are `await a2kit.log.info(CellStarted/CellEnded)` inline
on the loop thread — no `to_thread`. The synchronous `_LOGGER.log` inside `_emit`
runs `Handler.handle` → `Handler.emit` inline, so `LiveSink.emit` fires on the
loop thread, cooperatively, never interleaving with another cell's emit (no
preemption mid-sync-block).

**Rework — `LiveSink(logging.Handler)`:**

- `__init__`: call `super().__init__()` (this creates the handler's built-in
  `self.lock`, an `RLock`). Keep counters / stream / tty+unicode flags /
  heartbeat config.
- `emit(self, record)` — **sync**. `name = record.getMessage()`
  (`"CellStarted"`/`"CellEnded"`), `fields = getattr(record, "a2kit_fields", {})`.
  Dispatch to sync `_on_started(fields)` / `_on_ended(fields)`. **No explicit
  locking inside** — `logging.Handler.handle()` already wraps `emit()` in
  `self.lock`, so counter mutation + the console write are already serialized.
- **Drop `asyncio.Lock` entirely.** The only reader outside the logging-held
  lock is the heartbeat; it acquires the same `self.lock` (`with self.lock:`)
  around its counter read. `RLock` is reentrant and thread-safe, so this is
  correct whether emits stay on the loop thread or a future change moves them to
  a worker.
- **Heartbeat retained** as an `asyncio` task via async `__aenter__/__aexit__`
  in the bench loop — unchanged lifecycle. It never fights the handler model
  because `emit` touches no loop primitive; the heartbeat only shares counters,
  which `self.lock` covers.

The earlier "drop-heartbeat fallback" is **withdrawn** — there is no
threading/asyncio hazard to fall back from. Reusing the handler's own lock is
the whole trick.

## D-Ambient — `_ldd_ambient` collapse (Front B)

```python
# before
@contextmanager
def _ldd_ambient(sinks=()):
    with ldd_state_for_call(ctx=null_context(), events_enabled=True,
                            reports_enabled=False, sinks=sinks):
        yield

# after (sketch)
@contextmanager
def _ldd_ambient(handlers=()):
    added = [h for h in handlers]
    for h in added:
        a2kit_logger.addHandler(h)   # or app.log.add_handler when an app is in scope
    try:
        yield
    finally:
        for h in added:
            a2kit_logger.removeHandler(h)
```

No call scope is needed to emit: `a2kit.log.info` always does its synchronous
`_LOGGER.log` to `logging.getLogger("a2kit")` and only the optional wire-forward
half depends on a dispatch scope (None in the bench → early return). Bench cells
carry their own `total_ms`/`cost_usd` in the `CellEnded` payload, so the
framework's `elapsed_ms` (the only thing `bind_call_scope` would add) is not
consumed — we skip the scope.

**Logger handle CONFIRMED:** `a2kit.log.info` writes to `logging.getLogger("a2kit")`
(`emission.py:25 _LOGGER = logging.getLogger("a2kit")`), and `app.log.add_handler(h)`
is literally `logging.getLogger("a2kit").addHandler(h)` (`app_log.py:23`). The
bench has no `App`, so `_ldd_ambient` attaches the `LiveSink` handler to
`logging.getLogger("a2kit")` directly — the identical mechanism `app.log` uses.
`a2kit_logger = logging.getLogger("a2kit")` in the sketch above resolves to that.

## D-OtelHandler — mechanical (Front B)

`otel_sink(emission)` → `OtelHandler(logging.Handler)`:

```python
class OtelHandler(logging.Handler):
    def emit(self, record):
        name = record.getMessage()                 # was emission.name
        if not name.endswith("Ended"):
            return
        f = getattr(record, "a2kit_fields", {})     # was emission.payload
        step = f.get("step", "unknown")
        span = _TRACER.start_span(f"a2web.{step}")
        ...  # same attribute logic, off `f`
```

`_TRACER` lazy-load and the no-SDK no-op stay. The sink manifest
(`_manifests/sinks/__init__.py`) changes its `Sink` type from
`a2kit.packages.ldd.LddSink` to `logging.Handler`; `load_surface(...)` collects
handler instances and the boot path calls `app.log.add_handler(h)` for each.

## Migration order (load-bearing)

1. **Pin bump first** (`pyproject.toml` `a2kit>=0.43,<1`, tag `v0.43.0`) +
   `uv sync`. Capture the **red baseline** — unlike the v0.39 migration, this
   one will NOT be green on bump (v0.42/0.43 are breaking). Expect import
   errors from `a2kit.ldd` / `a2kit.packages.ldd` / `add_router` first.
2. **Front A** (App composition) — gets imports + boot working again.
3. **Front B** (LDD) — the bulk; do `otel_sink` + emit-site renames before the
   `LiveSink` rework so the green/red signal isolates the one hard edit.
4. **Front C** (name pins) — verify MCP wire names via a `make_client` round-trip
   (assert `ask`/`fetch_raw`/`refresh` resolve, not `web_ask`...).
5. **Front D/E** — lint-code grep (verify clean) + `CLAUDE.md` rewrite.
6. `make check` green, then `make install-global` so the operator's Claude Code
   picks up the new code (names unchanged, but the binary must rebuild).

## Unknowns resolved during exploration

- **Flat-name fitness functions — RESOLVED (no risk).** Audited all 13
  `tests/architecture/test_*.py`. None assert MCP tool-name shape. The only
  tool-introspecting test (`test_tools_return_pydantic_not_str.py`) keys off the
  `@a2kit.read/write` decorator + return annotation, never the name. Every other
  `.name` reference is AST-node introspection (`alias.name`, `node.name`). The
  `canonical_name_override` pins trip nothing. Front C task 0a downgrades from
  "investigate" to a one-line sanity re-grep.
- **`make_client` name resolution — RESOLVED (override IS reflected).** Traced
  in the `~/Workspaces/a2kit@v0.43.0` checkout: `tool.py:156` sets
  `desc.name = resolve_canonical_name(override, slug, leaf)`; `mcp/server.py`
  builds the `FunctionTool` under `desc.name` and `server.add_tool(tool)`;
  `testing/client.py:86` builds the client over the **same** production
  `build_mcp_server(app)`. So the test client's tool catalog keys on the
  overridden bare name. `runtime.py:458 _assert_unique_canonical_names` also
  enforces global uniqueness — our three pins are distinct, no collision. Task
  3b is therefore a real, passing assertion, not a hopeful one (exact form
  below).

## Risks (remaining)

All three exploration unknowns are now **resolved** (fitness functions, name
resolution, LiveSink locking) — see above. No open design unknowns remain; what
is left is execution mechanics:

- **Emit-site await correctness** — `a2kit.log.info` is async (not sync, as an
  earlier draft assumed). The `make check` red→green cycle and `ty` will catch
  any dropped/added `await` across the 28 sites. Low risk, high detectability.
- **Bench not in `make check`** — the LiveSink/runner rework (Front B 2f/2g)
  rides on `tests/capabilities/output_benchmark/test_live_sink.py` (a unit test,
  in `make check`) but the live `make bench` path is not gated. Run `make bench`
  once post-migration only if 2f/2g land (task 5e) to confirm the console
  renderer still draws.
