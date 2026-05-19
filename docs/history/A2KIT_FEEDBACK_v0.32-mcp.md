# a2kit feedback — round 8 (v0.32.x MCP transport)

From: a2web v0.6.0 on `a2kit v0.32.x`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Date: 2026-05-13
Scope: MCP transport correctness. CLI transport is unaffected; everything below is `tools/call` over stdio JSON-RPC.

This round is **one production blocker + two related transport-correctness asks**. The blocker silently 100%-breaks the MCP path for any tool that uses both `state: T` DI and `ctx: a2kit.ToolContext`. CLI works fine on the exact same tool — which is why it slipped past v0.32 release validation.

---

## Blocker — `_wrap_with_dispatch_hook` strips `ctx` before `_wrap_with_ldd_state` runs

### Repro

Any tool that declares both a container-resolved param (`state: AppState`) AND `ctx: a2kit.ToolContext`. Minimal reproducer:

```python
import a2kit

class State: ...

class R(a2kit.Router):
    slug = "demo"

    @a2kit.read()
    async def ping(self, *, msg: str, state: State, ctx: a2kit.ToolContext) -> dict:
        await a2kit.ldd.event("pinged", msg=msg)
        return {"msg": msg}

    tools = (ping,)

app = a2kit.App("demo")
app.add_router(R())
app.singleton(State, lambda: State())
```

CLI: `demo demo ping --msg=hi` → `{"msg":"hi"}`.

MCP `tools/call name=ping arguments={msg:"hi"}`:

```
{"jsonrpc":"2.0","id":3,"result":{
  "content":[{"type":"text","text":"Error calling tool 'ping'"}],
  "isError":true
}}
```

stderr shows:

```
TypeError: R.ping() missing 1 required keyword-only argument: 'ctx'
  at a2kit/packages/mcp/server.py:171 — result = fn(**resolved)
```

### What's happening

Build order in `packages/mcp/server.py:316-328`:

```
fn  →  _wrap_with_router_enrichers
    →  _wrap_with_dispatch_hook    # rewrites sig via wire_input_params — drops both state AND ctx
    →  _wrap_with_ldd_state        # reads kwargs[ctx] — finds None — sets ambient state with ctx=None
```

Call-time flow:

1. FastMCP introspects the outermost wrapped signature. `_wrap_with_ldd_state` doesn't rewrite the signature (it uses `functools.wraps`), and inherits the dispatch-hook's rewritten one. So FastMCP sees only wire params (`msg`) — never injects `ctx`.
2. `_wrap_with_ldd_state` does `kwargs.get(ctx_param_name)` → `None`. Calls `ldd_state_for_call(ctx=None, ...)` — sets `_LDD_STATE` with `ctx=None` (no fail; just degraded).
3. Inner dispatch-hook wrapper at `server.py:91`: `resolved = hook(fn, kwargs)` resolves `state` from the container, returns `{msg: ..., state: ...}` — **no `ctx`** because `ctx: ToolContext` isn't a container-registered type.
4. `result = fn(**resolved)` (`server.py:171`) → original tool body, missing required `ctx` kwarg → **TypeError**.
5. FastMCP stringifies the exception → bare `"Error calling tool 'ping'"`.

The CLI path doesn't hit this because `packages/cli/builder.py` constructs the call differently — it binds both `state` and `ctx` before invocation. The MCP path's `_wrap_with_dispatch_hook` was written for an earlier era when `ctx` was injected via `bind_context` *outside* of dispatch-hook signature mangling, and that ordering invariant was lost when `bind_context` was replaced by `_wrap_with_ldd_state`.

### Asks

1. **Fix the wrapper order or signature preservation.** Two clean shapes:
   - In `wire_input_params`, preserve `ctx_param_name` in the rewritten signature even though it's not a wire param. FastMCP then injects `ctx`, dispatch-hook passes it through `resolved`, `_wrap_with_ldd_state` reads it from kwargs (the existing code path), body receives it.
   - OR have `_wrap_with_dispatch_hook` resolve `ctx` from the dispatch-hook's context (`hook` already sees the FastMCP `Context` object in some form) and inject it into `resolved` alongside container-resolved DI.

   The first shape is one-line in `signature.wire_input_params`; the second is more code but keeps the signature schema-clean.

2. **Add a transport-parity test** to a2kit CI: minimal app with `state: T` (via `app.singleton`) + `ctx: ToolContext`, call the same tool over `a2kit.testing.client` AND a stdio MCP harness, assert identical responses. The exact code in the Repro block above plus an MCP JSON-RPC handshake is sufficient. This bug should never escape PR review again.

3. **Optional**: when `_wrap_with_ldd_state` observes `ctx is None` after `kwargs.get(...)`, raise a structured `A2KitMcpContextNotInjected` error with a hint pointing at the dispatch-hook signature-rewrite, rather than continuing with degraded ambient state. The current silent-degrade made this bug harder to localize.

### Impact on a2web

Total MCP outage in v0.6.0 for Claude Code users. Every `mcp__a2web__fetch` returns the bare error string — no diagnostics, no operator hint, no way for the agent to even know it should retry on CLI. The CLI path is unaffected, so users with terminal access can work around it; programmatic Claude Code consumers cannot.

We're holding three independent a2web changes (Reddit search handler, `[llm]` extras promoted to core, captcha pre-routing) on this fix — there's no point shipping MCP-facing features into a transport that universally errors.

---

## P1 — FastMCP error envelope discards exception class + message for tool-side exceptions

### What's happening

When a tool body or wrapper chain raises an uncaught exception (any class), FastMCP returns:

```json
{"content":[{"type":"text","text":"Error calling tool 'ping'"}],"isError":true}
```

No exception class, no message, no path. Rich traceback prints to stderr but never reaches the wire. Even with `App(debug=True)` — which sets `mask_error_details=False` per `server.py:294` — the wire envelope still collapses to the bare string under the FastMCP version pinned in v0.32.x.

### Asks

1. **a2kit owns the contract; wrap dispatch and translate uncaught exceptions into structured envelopes.** Minimum payload: `{class: "TypeError", message: "ping() missing 1 required keyword-only argument: 'ctx'"}`. With `App(debug=True)`: also `{traceback: "<rendered>"}`. Don't depend on FastMCP's `mask_error_details` semantics — they've shifted between FastMCP minor versions and round 6 already burned us on a similar dependency.

2. **Document the contract** in OPERATIONAL_CONTRACTS: *"a2kit guarantees uncaught tool exceptions reach the wire with `{class, message}` always, and `{traceback}` when `debug=True`."* Then a2kit owns the guarantee regardless of FastMCP internal behavior.

### Impact on a2web

Debugging MCP-only failures currently requires `gtimeout … 2>stderr.log` JSON-RPC harnesses to extract the real exception class. Every user bug report of "MCP broken" forces us to run the local handshake ourselves. Structured error envelopes would let users self-report with the actual class + message in their first ticket.

---

## P2 — `Context`-typed parameter contract isn't doc-tested across transports

### Context

`CLAUDE.md` (a2web project conventions, derived from a2kit's OPERATIONAL_CONTRACTS):

> *"Tool body must declare `ctx: a2kit.ToolContext` for the dispatcher to bind it — phases just emit, never receive ctx."*

This contract is honored over CLI. It silently breaks over MCP (the round-8 blocker above). The converse edge — a tool that does NOT declare `ctx` but body code calls `a2kit.ldd.event(...)` anyway — produces `AmbientContextMissing` over CLI; we haven't probed its MCP behavior but the symmetry suggests it's worth a doc-test.

### Asks

1. **Add an MCP/CLI transport-parity matrix to a2kit's test suite** — same tool, both transports, four combos:
   - `state` only (no ctx)
   - `ctx` only (no state)
   - both `state` + `ctx`
   - neither

   Assert each works identically over both transports, with the same exception classes on the same misuses.

2. **Cross-link OPERATIONAL_CONTRACTS § "Context binding" to the test.** When the contract evolves, the test evolves with it.

---

## Related — promote deferred wish #6 (`_LDD_STATE` accepts `ctx=None` for opt-out)

Round-8 blocker analysis surfaces something: `_wrap_with_ldd_state` already sets `_LDD_STATE` with `ctx=None` in the broken case, but `a2kit.ldd.event` then crashes on the `else: ctx._emit(...)` branch when `ctx` is None. If wish #6 (in `A2KIT_WISHES_DEFERRED.md`) had landed, the broken case would still fail (TypeError on the body's `ctx` param), but post-blocker-fix, tools that legitimately want to opt out of LDD over MCP would have a graceful path.

Worth re-prioritizing wish #6 once the round-8 blocker fix lands — they're complementary.

---

## What we'd ship in a2web once round-8 lands

- Re-enable the MCP path with full LDD events (we can't ship without observability).
- Land the Reddit search handler, LLM-OOTB packaging (incl. bundling `claude-agent-sdk` despite its ~210MB footprint — most users are inside Claude Code and rely on its OAuth path), and captcha pre-routing.
- Delete `BACKLOG.md` entry "MCP transport broken, awaiting a2kit fix".

## Not asking for

- New API surface. The asks are "honor existing contracts under the MCP transport".
- Documentation-only fixes. The blocker is code.
- Faster releases. v0.32 cadence has been fine; correctness > speed.

---

## Migration / release context

a2web v0.6.0 is the first release fully on a2kit v0.32, shipped 2026-05-13. The MCP path was validated against CLI parity on early-v0.32 prereleases but the `_wrap_with_ldd_state` reordering appears to have landed in a later v0.32 patch; we caught it in production on a real Claude Code session immediately after v0.6.0 ship. CLI continues to work for all 12 of a2web's regression URLs; MCP fails on 100% of them.
