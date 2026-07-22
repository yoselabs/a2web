# a2kit feedback — final round (2026-07-22): the last consumer has left

> **Status: TERMINAL.** a2web no longer depends on a2kit. This is not a bug
> report and there is nothing to fix — it is the notice a2kit asked for.
> a2kit can drop maintenance mode and proceed with dissolution.
>
> Change: `openspec/changes/sunset-a2kit-dependency/` (a2web repo).
> a2web now composes on `fastmcp.FastMCP` directly.

## What a2web took over

a2kit's spine was replaced by roughly 300 lines a2web owns:

| a2kit | a2web now |
|---|---|
| `App` subclass + `routers` ClassVar | `server.build_mcp_server()` |
| `app.provide(...)` DI container | `components.build_components()` — one composition root |
| implicit wire/injected parameter split | explicit tool signatures (`routers.py`) |
| `Lazy[T]` from the container | `lazy.Lazy` + `scope.memoized(factory)` |
| resource entry on resolution | `scope.ResourceScope` (LIFO unwind) |
| `EncodingPlan` inference + `FormatRoutingMiddleware` | `wire.py` — a literal `_TSV_FIELDS` table |
| `McpErrorRenderStage` + envelope middleware | `error_wire.py` |
| `a2kit.log` | `a2web.log` |
| `encode_tsv` | vendored `_tsv_compat.py` (leaves with shelf `lean-wire`) |
| `a2kit.testing.client` | `tests/_helpers/mcp.py` |
| the generated Typer CLI | `cli.py`, derived from `mcp.list_tools()` |

`a2effect` is now a direct dependency rather than transitive.

## What a2kit was right about

Three things did not survive contact with hand-wiring as *convention*, so
a2web had to pin each with a test that a2kit gave structurally:

- **Cold-start laziness.** a2kit's container made "don't construct the
  browser or the LLM on a cache-served `query`" structural. Hand-wired,
  it is one `await` away from being lost — `test_cold_start_laziness.py`.
- **One composition root.** `bootstrap_state` had already drifted from
  the container once, in v0.22. `test_one_composition_root.py`.
- **Resource lifecycle.** The `ResourceScope` teardown discipline is real
  work: aiosqlite's worker thread is non-daemon in production, so a CLI
  command that skips `aclose()` prints correct output and then **hangs
  forever**. a2kit's `serve` never let a2web meet that failure.

## What was actually lost

- **`a2kit lint rego`.** No replacement. Filed in a2web's `BACKLOG.md`
  (2026-07-22) as a real capability loss, not a deliberate drop.

## Three encoder defects a2web filed and could not work around

All three were fixed on the way out, in `wire.py`, and are recorded here
so a2kit's successor substrate does not reintroduce them:

1. **Presence guard.** A pruned field was resurrected as `"\n"` plus a
   `_<name>_format` sidecar. Fixing this alone took the minimal success
   payload from 11 keys to 2.
2. **Already-a-string guard.** A populated `other_pages`, handed over
   pre-encoded, was overwritten with the empty marker.
3. **Row-shape guard.** `encode_tsv` expected `BaseModel`-or-dict rows
   and raised on a `list`.

## The lesson worth carrying forward

a2web's wire golden froze `~95%%` — a typo in a description every calling
agent reads — perfectly, through seventeen rounds of wire review. It took
rendering the same string through a *different* surface (`--help`, in the
derived CLI) to see it.

A golden proves a surface has not **changed**. It says nothing about
whether it was right when captured.

## Numbers

`make check` green at `ce58272`: 1233 passed, coverage 90.32%, 37
architecture tests. No behavioural regressions attributable to the
sunset; two shipped bugs were found and fixed *by* it (the 404'd
container `/health` route, and a `__version__` stale by 47 releases).

Thanks for six months of substrate. It carried a2web from nothing to a
shipping product, and the parts worth keeping are moving to the shelf,
not being thrown away.
