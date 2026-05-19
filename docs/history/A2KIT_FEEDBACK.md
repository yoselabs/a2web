# a2kit feedback — round 7

From: a2web v0.7 (post v0.28→v0.32 migration) on `a2kit v0.32.0`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Context: rounds 1-6 addressed across v0.24 → v0.32.0, with v0.28.1 + v0.29.0/.1 + v0.30.0 + v0.31.0 + v0.32.0 shipping in a tight 2026-05-12 → 2026-05-13 window. Thank you — the lifespan-over-hooks rewrite, explicit Router contract, ambient-ctx LDD, `TestClient.override` / `call_wire`, and the `_meta` namespace docs all landed cleanly. The docstring-pull reversal in v0.30 was the right call.

This round is **one production bug + three round-7 wishes that surfaced during the v0.32 migration**. None blocks anything; the bug is the only thing that breaks a real user-facing command.

---

## Bug — `<app> health` crashes when pytest isn't installed

### Repro

```
$ uvx --from . a2web health
...
File ".../a2kit/packages/cli/builder.py", line 475, in health_cmd
    from a2kit.packages.testing.client import client as _client
File ".../a2kit/packages/testing/__init__.py", line 16, in <module>
    from a2kit.packages.testing.fixtures import app, cassette
File ".../a2kit/packages/testing/fixtures.py", line 14, in <module>
    import pytest
ModuleNotFoundError: No module named 'pytest'
```

100% reproducible on a fresh install without dev extras. Any consumer who installs a2web (or any a2kit app) via `pipx`, `uv tool install`, `uvx`, or system Python and runs the auto-generated `<app> health` subcommand hits this on the first invocation.

### What's happening

`packages/cli/builder.py:475` imports the test client to build the health command. The test-client import chain ultimately reaches `a2kit/packages/testing/fixtures.py`, which `import pytest`s at module load (line 14). `pytest` is a dev/test dependency, not a runtime dependency of a2kit.

### Asks

1. **Guard the pytest import** — make it lazy, conditional, or `TYPE_CHECKING`. A minimal fix:

   ```python
   # a2kit/packages/testing/fixtures.py
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       import pytest  # only for type hints
   ```

   …or move the pytest-using fixtures into a separate module that's not auto-imported by `packages/testing/__init__.py`.

2. **Decouple the health subcommand from the test client.** `health_cmd` reaches into `packages/testing/client` to build an in-process invocation. The health probe doesn't need a test client — it needs the App's container and the registered health checks. A small refactor would let `<app> health` run without ever loading the testing surface.

3. **Add a smoke test for the production CLI without dev extras.** A 5-line CI job that does:

   ```
   uv venv --no-dev-deps
   uv pip install . --no-deps
   uv pip install <runtime deps only>
   ./venv/bin/<app> health
   ```

   …catches this regression class.

### Impact on a2web

Currently `a2web health` is broken end-to-end for any non-dev install. The `serve` and `web fetch` paths are unaffected (verified — they don't reach the testing import chain). Low blast radius for a2web specifically (operators rarely invoke `health` directly), but it's a foot-gun for any new a2kit consumer.

---

## Wish 1 — `app.singleton(T, factory, teardown=fn)` for singleton-owned cleanup

### Context

Surfaced during the v0.32 lifespan rewrite. With `@app.on_shutdown` removed (v0.31), every consumer with async resources hand-rolls cleanup in the lifespan body's `finally` block:

```python
@asynccontextmanager
async def lifespan(app):
    state = app.container().resolve(AppState)
    await state.sqlite._ensure()
    try:
        yield
    finally:
        # Reverse-of-open order. Each close error-isolated.
        for closer in (state.llm_extractor.close, state.browser_pool.close, state.sqlite.close):
            try:
                await closer()
            except Exception:
                pass
```

Three resources, three closers. Scales linearly with resource count. Every consumer reinvents:
- the error-isolation wrapping
- the close-ordering convention
- the "what if the resource was never resolved" guard

### Proposal

```python
app.singleton(SqliteResource, factory=build_sqlite, teardown=lambda r: r.close())
app.singleton(BrowserPool, factory=build_pool, teardown=lambda p: p.close())
app.singleton(LlmExtractorResource, factory=build_llm, teardown=lambda x: x.close())
```

Semantics:
- `teardown` is invoked at lifespan exit on every singleton that was *resolved* during the app's lifetime. Unresolved singletons don't trigger their teardown.
- Order is reverse-of-registration (LIFO).
- Each teardown is shielded — exceptions are logged via `a2kit.ldd.error` (under `a2kit.lifecycle` or similar) with traceback, and siblings continue to unwind.
- The user's lifespan body just yields (or runs business logic that doesn't touch resource cleanup).

### Why it matters

If a2kit ships first-class teardown, every a2kit app with N async resources deletes O(N) LOC of repetitive close-ordering + error-isolation boilerplate. Same logic applies as the round-5 "async resource pattern" wish: the workaround is mechanical, the framework can own the mechanism.

### Alternative shape

If `teardown=` proves complex (e.g., needs DI-injected helpers), an `app.on_teardown(T, fn)` registry would work too — same effect, separate registration call.

---

## Wish 2 — Decorator-time enforcement of `Router.tools` tuple completeness

### Context

v0.31's CHANGELOG notes:

> a decorated-but-unlisted method silently does NOT register (a follow-up lint rule will flag this drift statically)

The lint rule is "follow-up" — not yet shipped. Without it, adding a `@a2kit.read/write/list_/tool`-decorated method to a Router and forgetting to add it to the `tools` tuple silently produces a tool that's invisible on every transport. No error, no warning at decoration time. No error at Router init (the orphan method just isn't enumerated).

### Asks

Either of:

1. **Ship the planned static lint rule.** Walk every `Router` subclass, collect `@a2kit.read/write/list_/tool`-decorated methods, diff against `tools` tuple. Emit `A2K-ROUTER-ORPHAN` (or similar) on drift. Runs at lint time, no runtime cost.

2. **Raise at `Router.__init__`** if any class-level callable has `_a2kit` meta but isn't in `tools`. Catches at App composition; same as the existing `slug`/`tools`-required checks already there.

The two are not mutually exclusive — lint catches it at IDE / pre-commit time; runtime check catches it for callers who skip lint.

### Why it matters

a2web has only one tool today so the drift is easy to spot mentally. But the v0.31 explicit-Router-surface design assumes the framework can trust what authors wrote *and* what they didn't write. Silent absence is the worst failure mode — the tool is gone, but the developer doesn't notice until an MCP client reports "no such tool."

---

## Wish 3 — Sharper `AmbientContextMissing` message when ctx is None vs missing scope

### Context

Surfaced during the v0.32 migration. I initially stripped `ctx: a2kit.ToolContext` from `WebRouter.fetch` along with the phase functions. All transports broke with:

```
a2kit.exceptions.AmbientContextMissing: a2kit.ldd.event called outside an active
tool dispatch. LDD primitives only work inside a tool body (or any code reached
from one). Move the call into a tool, use the test harness's
ldd_state_for_call(ctx=...) context manager, or remove the call.
```

The actual fix was to re-declare `ctx: a2kit.ToolContext` on the tool body (per OPERATIONAL_CONTRACTS Q8: "active dispatch is the conjunction of an `ldd_state_for_call` scope **and** a declared ctx param"). But the error message says "called outside an active tool dispatch" — which is misleading. The dispatch IS active; what's missing is the `ctx` parameter declaration on the tool.

### The two distinct failure modes today produce the same message

- **Mode A**: LDD primitive called from module-level code, `@health_check` (without ctx param), or any pre-dispatch context. The contextvar isn't set at all. → Correct message: "called outside an active tool dispatch."
- **Mode B**: LDD primitive called from inside a tool body, BUT the tool body didn't declare `ctx: ToolContext`. The contextvar IS set (by `ldd_state_for_call`), but its `ctx` field is `None`. → Current message is wrong. Better message: "tool body called LDD primitive but did not declare `ctx: a2kit.ToolContext` parameter — add it to the signature, or remove the LDD call."

### Proposal

Distinguish the two paths in `_require_ambient_state` (or wherever the raise happens):

```python
def _require_ambient_state(primitive_name: str) -> _LddState:
    state = _LDD_STATE.get(None)
    if state is None:
        raise AmbientContextMissing(
            f"{primitive_name} called outside an active tool dispatch. ..."
        )
    if state.ctx is None:
        raise AmbientContextMissing(
            f"{primitive_name} called from a tool body that did not declare "
            f"'ctx: a2kit.ToolContext' as a parameter. Add the parameter to "
            f"the tool signature (the dispatcher will bind it ambient), or "
            f"remove the LDD call."
        )
    return state
```

Pure DX — points the developer at the actual fix without them having to grep OPERATIONAL_CONTRACTS Q8.

---

## Soft note — v0.32 migration was the smoothest of the six rounds

A2kit v0.32 was the third breaking release in 30 hours (v0.30, v0.31, v0.32 all on 2026-05-12 → 2026-05-13). For a2web — which holds the only consumer surface most of these breakings touch — the cumulative migration was **~250 LOC across 9 files** + one autouse pytest fixture, executed cleanly in one session. The breaking changes were each individually small, well-documented, and produced loud errors that pointed at the fix.

Specifically:
- `a2kit.Param` removal: error message was "module 'a2kit' has no attribute 'Param'" — instant pointer to migration.
- `slug`/`tools` missing: error named the Router class, gave an example.
- FastMCP build error: documented its own migration in the exception text.
- `AmbientContextMissing`: pointed at OPERATIONAL_CONTRACTS Q8 (modulo Wish 3 above).

If there's a takeaway: a2kit's "loud failure with embedded migration hint" pattern is excellent. The bug above (`<app> health` + pytest) is the one place that doesn't follow this pattern — silent at install time, blows up at first invocation with a stack trace that doesn't mention "you need pytest, or this is a a2kit bug."

---

## What we're NOT asking for this round

To save you reading: explicitly not blocking, parked in `docs/history/A2KIT_WISHES_DEFERRED.md`:

- Streaming response API (Q6, round 3) — no current pressure
- `@a2kit.read(timeout="60s")` decorator kwarg (round 3) — `anyio.fail_after` works
- Per-tool retry policy — owned at the tier layer (a2web)
- Built-in caching layer — hishel works
- Auto-reload — `watchexec` is the documented answer
- `Optional[T]` / `Union` as singleton key — **verified working** in v0.32; no fallback `Handle` dataclass needed

---

## Migration status

a2web v0.6.0 → v0.7 (unreleased) on a2kit v0.32.0 — migration shipped in `openspec/changes/archive/2026-05-13-a2kit-v032-migration/`.

- 387 tests green
- coverage 89.45% (≥85% gate)
- `claude mcp list` shows a2web ✓ Connected as global MCP server (the round-6 blocker)
- CLI smokes pass across raw / site_handler / handler-with-archive paths

Happy to contribute the smoke test for `<app> health` without dev extras, run experimental APIs against the suite, or repro any of the wishes with a concrete branch.

Thanks again for the cascade.
