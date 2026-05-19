# a2kit feedback — round 6

> **Status (2026-05-13):** Shipped in a2kit v0.28.1 (FastMCP fix, `_meta` docs)
> + v0.29.0/.1 (every round-5/6 ergonomic gap)
> + v0.30.0 (docstring-pull reversion — our round-5 caution about silent
>   description drift was vindicated by upstream removal within 24h)
> + v0.31.0 (Param removal, lifespan-over-hooks, explicit Router contract)
> + v0.32.0 (Typer CLI, namespace trim, `visibility` tier).
> a2web migrated in change `2026-05-13-a2kit-v032-migration`.

From: a2web v0.6.0 on `a2kit v0.28.0`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Context: rounds 1-5 addressed across v0.24 → v0.27.2. Resource pattern, type-driven format routing, sink registration, typed emit, DI-aware lifecycle, in-process test client, OPERATIONAL_CONTRACTS — all in place. Thank you.

This round is **one blocker + status check on round-5 ergonomic gaps + two small new frictions found while shipping v0.6.0**.

---

## Blocker — `a2kit serve` is broken against the current FastMCP release

### Repro

```
$ pip install 'a2kit==0.28.0'     # pulls fastmcp 3.2.4 transitively
$ a2web serve                     # any app calling a2kit.run with the MCP path
...
File ".../a2kit/packages/mcp/server.py", line 320, in build_mcp_server
    tool.disable()
File ".../fastmcp/utilities/components.py", line 218, in disable
    raise NotImplementedError(
NotImplementedError: Component.disable() was removed in FastMCP 3.0.
Use server.disable(keys=['tool:_meta.health@']) instead.
```

100% reproducible. Any consumer who installs a2kit fresh today hits this on first `serve` invocation. The CLI side (`a2web web fetch …`) is unaffected because it doesn't build the MCP server.

### What's happening

`a2kit/packages/mcp/server.py:320` calls `tool.disable()` on `_meta`-tagged tools to hide them from the default tool list. FastMCP 3.0 removed `Component.disable()`; the new API is `server.disable(keys=[...])` per the error message itself.

### Asks

1. **Fix the call site** — the FastMCP error message documents the migration path verbatim. Roughly:

   ```python
   # current
   if is_meta:
       tool.disable()
   server.add_tool(tool)

   # proposed
   server.add_tool(tool)
   if is_meta:
       server.disable(keys=[f"tool:{meta.tool_name}"])
   ```

2. **Pin a FastMCP floor in `a2kit`'s `pyproject.toml`.** Without a floor like `fastmcp>=3.0` (or `>=3.0,<4`), downstream lockfiles drift and the same break recurs whenever FastMCP cuts another major. Right now a2kit silently inherits whatever's resolvable, which is how this slipped.

3. **One smoke test that does `build_mcp_server(app)`** against a trivial app with one router + the auto-built health tool. Would have caught this. Happy to contribute the test if useful — it's two `assert`s.

### Impact on a2web

Currently blocking the "register a2web as a global Claude Code MCP server" milestone. We can pin `fastmcp<3.0` locally as a workaround, but that's a downstream lockfile patch for an upstream regression. Once 2 + 3 land we drop the pin.

---

## Status check — round-5 gaps after v0.28

Round 5 (post-v0.27.2) raised four ergonomic gaps. Quick check on each from v0.28's vantage:

| Gap | Status from a2web's view | Notes |
|---|---|---|
| 1. `@app.async_resource` | Not seen in v0.28 changelog we tracked | Three Resource classes still hand-rolled (`SqliteResource`, `BrowserPool`, `LlmExtractorResource`). ~80 LOC of double-checked-locking boilerplate stands. |
| 2. Ambient `ctx` via ContextVar | Not seen | Nine phase functions still thread `ctx` purely for `ldd.event`. `null_context()` branch in `fetch()` still present. |
| 3. `app.testing.override(T, fake)` | Not seen | `monkeypatch.setattr(state.llm_extractor, "_extractor", …)` + `type: ignore[assignment]` pattern still used in ~15 test sites. |
| 4. Param verbosity / docstring pull | Not seen | `routers.py` still 80% `Annotated[T, a2kit.Param(...)]` wrappers. |

If any of these landed in v0.28 under a different name, please point us at the release notes and we'll migrate. If they're still backlog: same priority as before — none blocking, all compounding.

---

## New friction 1 — `_meta` tool naming convention is undocumented in OPERATIONAL_CONTRACTS

While debugging the FastMCP break I went looking for what `_meta`-prefixed tools are, why they're hidden, and whether app authors can register their own. The string `_RESERVED_TOOL_NAME_PREFIX` and the "hidden from default list" behavior aren't in `OPERATIONAL_CONTRACTS.md` or the README.

Concretely, the questions a v0.28 consumer can't answer from docs:

- Is `_meta.*` a closed namespace owned by a2kit, or can an app define its own `_meta.foo`?
- What's the contract for "hidden tools" — are they callable by name via MCP if a client knows the name? Filtered server-side?
- Does the `_meta` tag affect CLI surface (`a2web _meta …` is visible in `--help`) the same way as MCP?

The fact that `a2web _meta --help` exposes them in CLI but FastMCP hides them on the MCP wire is a deliberate split, and it's a reasonable design — just not written down.

**Ask:** one paragraph in OPERATIONAL_CONTRACTS clarifying the `_meta` namespace contract. Less than 200 words.

---

## New friction 2 — `a2kit.testing.client` lacks a way to inspect the MCP wire payload

We use `a2kit.testing.client(app)` heavily — 374 tests, mostly happy. One gap: `client.call("WebRouter.fetch", url=…)` returns the Python object the tool returned (good for assertions on `FetchResponse.status`), but doesn't expose what the **MCP wire-encoded** payload would look like.

That matters because the type-driven format routing (v0.22+) means the wire form can diverge from the Python form (Page[T] paginates, lists become TSV, etc.). When a downstream MCP client reports "the JSON I got back doesn't match what your tests assert," we currently can't reproduce the wire payload in-process — we have to spin up `a2web serve` and call it over actual stdio.

**Ask shape (one of):**

```python
# (a) opt-in flag
result = await client.call("WebRouter.fetch", url=..., wire=True)
# result is the formatter-encoded payload (dict / str), not the raw object

# (b) sibling method
wire = await client.call_wire("WebRouter.fetch", url=...)
```

We'd use this in ~5 tests that currently have to assert "the formatter behaves correctly" by reading the formatter's own source — which is testing the wrong thing.

---

## What we'd delete in a2web if all the above shipped

| Item | LOC |
|---|---|
| FastMCP pin workaround (when we apply it) | 1 line in pyproject, removed |
| Resource boilerplate (round-5 gap 1) | ~80 |
| `ctx` threading (round-5 gap 2) | ~30 |
| Test override monkeypatches (round-5 gap 3) | ~15 |
| `Annotated[…]` wrapping (round-5 gap 4) | ~50 |
| Custom wire-encoding test harness | ~20 (proactive — never written because no API) |
| **Total** | **~195 LOC + framework friction** |

---

## Not asking for

To save you reading:

- Per-tool retry / circuit breaker (a2web owns this at the tier layer with purgatory).
- Built-in HTTP caching (hishel works fine).
- Auto-reload (`watchexec` answers it).
- Cancellation cleanup (tool-author responsibility — agreed).
- A streaming response API (Q6, raised round 3) — still want it eventually, but not this round; nothing changed.

---

## Migration / release context

- a2web v0.6.0 shipped 2026-05-12 on `a2kit v0.28.0`.
- Headline a2web features in v0.6.0: extraction-quality eval harness (Reader-LM v2 baseline), Reddit coverage sweep (permalink focus, crosspost, archive escalation, short URLs), 10-entry starter corpus.
- 374-test suite green; coverage ≥85% gate holds.
- No a2kit API surface regressions found in v0.28 — only the FastMCP transitive break.

Happy to contribute the smoke test for the MCP build path, run experimental APIs against the suite, or repro any of the round-5 items with a concrete branch.

Thanks again.
