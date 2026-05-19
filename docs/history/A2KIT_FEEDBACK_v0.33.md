# a2kit feedback — round 9 (v0.33.0 review)

From: a2web v0.6.0 on `a2kit v0.33.0`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Date: 2026-05-14
Context: read after rounds 7 and 8 (`A2KIT_FEEDBACK.md` and `A2KIT_FEEDBACK_v0.32-mcp.md`). This round is short and load-bearing: one **regression note** about what v0.33 didn't address, one **undocumented breaking change** we discovered the hard way, and one **changelog-discipline ask** so we don't keep finding silent breaks by running things.

The v0.33 prettification work is good. The footgun guards (TypeError on `@a2kit.read(idempotent=...)`, decoration-time `@list_` constraints, the singleton-decorator removal) are exactly the kind of "loud failure with embedded migration hint" we asked for in earlier rounds. The README CI gate is overdue and welcome. Not asking for any of that to change.

---

## Status — round-8 asks did NOT land in v0.33

We filed round 8 (`A2KIT_FEEDBACK_v0.32-mcp.md`) on 2026-05-13. v0.33 tagged the same day. The round-8 fixes did not make this release. Confirmed by direct repro against v0.33 source:

```
$ pip install a2kit==0.33.0
$ python -c "<minimal app with state: T + ctx: ToolContext>" serve
$ # tools/call ping msg=hi
{"content":[{"type":"text","text":"Error calling tool 'ping'"}],"isError":true}

stderr:
  TypeError: R.ping() missing 1 required keyword-only argument: 'ctx'
    at a2kit/packages/mcp/server.py:171 — result = fn(**resolved)
```

Identical to v0.32. `_wrap_with_dispatch_hook` still rewrites the signature via `wire_input_params`, which routes through `user_input_params` which explicitly drops `ctx_name` (`signature.py:79`). `_wrap_with_ldd_state` reads `kwargs.get(ctx_param_name) → None`. Dispatch hook resolves `state` from container but `ctx` is never re-injected. Original fn raises TypeError on the missing kwarg.

**No new asks here** — the three round-8 asks (MCP wrapper-order fix, structured error envelopes, transport-parity tests) all stand. Cross-link this file from the round-8 file so a future reader knows the bug survived v0.33.

What's worth flagging for v0.33-specifically: the round-8 file was published the same day as v0.33, so it's plausible the asks were received after the release cut. A line in the v0.34 plan / openspec change explicitly acknowledging round 8 would close the loop.

---

## Undocumented breaking change — `TestClient.call()` renamed to `.invoke()`

### Repro

```python
from a2kit.packages.testing.client import client as make_client
async with make_client(app) as c:
    out = await c.call("demo.ping", msg="hi")
    #               ^^^^
    # AttributeError: 'TestClient' object has no attribute 'call'
```

`TestClient` in v0.33 exposes: `app`, `call_wire`, `events`, `invoke`, `logs`, `override`, `progress`, `render_as`, `reports`, `tools`. No `.call`. Replacing `.call` with `.invoke` makes the same call succeed.

### Why this matters

- `client.call(tool, **kwargs)` is the canonical in-process call documented across previous rounds (round 6 referenced it; round 7 referenced it; OPERATIONAL_CONTRACTS Q1 demos use it; a2web's CLAUDE.md uses it as the prescribed pattern: *"a2kit's in-process test client is the default: `client = a2kit.testing.client(app); await client.call('WebRouter.fetch', url=...)`"*).
- The v0.33 changelog migration table has **13 rows** but does not mention this rename.
- It silently breaks **every consumer's test suite** the moment they bump the pin.

### Ask

1. **Add to v0.33 changelog (retroactively, with a v0.33.1 doc-only release if needed)**:

   | before | after |
   |---|---|
   | `await client.call(tool, **kwargs)` | `await client.invoke(tool, **kwargs)` |

2. **If the rename was intentional**, OPERATIONAL_CONTRACTS or a docstring should explain the why (presumably alignment with MCP's `tools/call` vs. the more general "invoke a tool through the test client" — but the asymmetry isn't obvious).

3. **If the rename was unintentional**, add `TestClient.call = TestClient.invoke` as an alias in v0.33.1. Renaming the canonical entry point of the canonical test client is exactly the kind of consumer-interface change ADR-0003 / the consumption-interface audit was written to catch.

### Impact on a2web

Trivial — five test files need `.call` → `.invoke`. But we found it by running and watching things break, not by reading the changelog. That's the failure we care about, not the rename itself.

---

## Ask — extend the README-drift CI gate to cover TestClient + connections surface

### Context

v0.33's `tests/test_readme_symbol_drift.py` parses README.md and asserts every claimed public symbol resolves on the live module surface. Great gate. Caught ten stale `@app.on_startup` / `Surface` enum references in this pass.

But the README isn't the only canonical source. Round 6 introduced `a2kit.testing.client` + `client.call` + `client.override` + `client.call_wire` as the documented in-process API. Round 8 implicitly relied on it. The `.call → .invoke` rename slipped past both PR review AND the round-7-shipped README drift gate, because the README probably calls it via the lazy `a2kit.testing` accessor without naming `.call` specifically.

### Asks

1. **Extend the symbol-drift gate to per-class method surface** for at least these canonical types: `TestClient`, `App`, `Router`, `ToolContext`, the verb decorators. Walk every method name claimed in the README's code blocks (not just `a2kit.X` references) and assert it exists.

2. **OR ship a `tests/test_canonical_apis.py`** that exercises the documented call shapes from CLAUDE.md / OPERATIONAL_CONTRACTS / README in a single concrete script — so renaming `.call` to `.invoke` fails that test even if the README is updated. Renames-with-test-updates are fine; silent renames-without-test-updates are the failure mode.

3. **Cross-link with round-8 ask #2** (transport-parity tests). The same fixture app that proves CLI/MCP parity could also exercise the documented public APIs end-to-end, killing two failure modes with one harness.

### Why it matters

v0.28 → v0.33 has been six releases in two days. The cadence is great. The cost of a silent rename in that cadence compounds: every consumer that bumps the pin runs into an undocumented break, files a feedback round, churn-cycles back to the maintainer. A canonical-API drift gate makes the cadence sustainable.

---

## Minor — `App(health_tool=True)` semantics in v0.33

### Observation

v0.33 changelog row: *"`App(health_tool=True)` + checks → drop the flag — `@app.health_check` auto-installs the tool"*. The "Changed" section clarifies: *"`App(health_tool=True)` remains accepted (no-op when checks are also registered) for apps that want the tool present with zero checks."*

Soft-deprecation is the right call here (no break, just dead surface). Two follow-ups:

1. **Document the no-zero-checks behavior**: what does `_meta.health` return when `health_tool=True` but no `@app.health_check` is registered? OPERATIONAL_CONTRACTS should specify (probably: `{status: "ok", checks: []}`).
2. **Schedule its removal**: emit a `DeprecationWarning` from `health_tool=True` in v0.34 with a removal target. The CLAUDE.md template still has `App("a2web", health_tool=True, lifespan=lifespan)`, and other consumer repos likely do too.

Not a blocker, just keeping the dead-surface-pruning momentum from v0.33 going.

---

## What we'd do in a2web from this round alone (independent of round-8 fix landing)

- Bump pin to `a2kit>=0.33,<1` once round-8 MCP fix lands (combined migration).
- Drop `idempotent=True` from `@a2kit.read` in `routers.py:21` (forced by v0.33 — would raise TypeError on import).
- `client.call` → `client.invoke` in tests (forced).
- Remove `App(health_tool=True)` from `server.py:46` (cosmetic — the auto-install via `@app.health_check` makes it dead).

## Not asking for

- Reverting any v0.33 footgun guards or dead-surface removals. They're correct.
- Faster releases.
- New API surface.

## Migration / release context

a2web stays on a2kit v0.32.0 until v0.34 ships with the round-8 fixes. We'd rather sit on the (working) round-7 gaps than do two adjacent migrations across the v0.33 prettification breaks AND the v0.34 MCP fix. If v0.34's scope expands beyond the round-8 asks, please flag it in the openspec change so we can plan a single coordinated cut.
