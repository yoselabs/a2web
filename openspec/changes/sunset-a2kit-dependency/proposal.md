## Why

**a2kit is dissolving, and a2web is the last consumer holding it open.**

a2kit ADR 0032 retires the `App` framework. Its delivering OpenSpec change carries
a Direction update (2026-07-15) that supersedes the ADR's own original plan:

> *"The destination of the surviving substrate is **the shelf**, not FastMCP
> upstream. a2kit **dissolves**; it does not re-found as a FastMCP-extras helper
> library — a fresh 3.x major still absorbing framework territory would eat a
> helper package the way it ate the framework."*

The sibling consumer a2kay **completed its own sunset** (archived
`2026-07-16-sunset-a2kit-dependency`): its `pyproject.toml` now depends on
`fastmcp>=3.4` directly with zero a2kit. That change's design explicitly names the
debt this change pays:

> *"Out of THIS program, but named now: dropping the DI container +
> `a2kit.testing` **orphans a2web**… **a2kit stays in maintenance for a2web until
> a2web migrates** (its own later program)."*

This is that program.

**The migration is far smaller than the architecture implies.** Measured, not
assumed:

- **~80% of the composition spine is ceremony for a2web's shape.** a2web uses one
  scope, ten types, and a dependency graph fully known at authoring time. a2kit's
  599-line `Container` exists to resolve *unknown* graphs. Irreducible substrate:
  **60–90 lines**.
- **The parallel composition root already exists and already wins.**
  `state.py::bootstrap_state` and `tests/conftest.py::make_default_bundle` build
  the identical object graph with plain constructor calls, serving 401 tests plus
  the eval CLI plus the bench harness. **The DI container is the minority
  construction path in a2web's own codebase.**
- **Only 2 of 5 `Lazy[T]` seams are load-bearing.** Every resource is already
  internally lazy behind an idempotent `_ensure()` under its own lock;
  `LlmExtractorResource.__aenter__` is literally `return self` and
  `ZendriverBackend.__aenter__` is a no-op. The two that matter:
  `Lazy[BrowserBackend]` (eager entry launches a browser driver at boot) and
  `Lazy[Provider]` (its factory *raises* on a keyless install — eager resolution
  turns a degraded-but-serving deploy into a boot crash).
- **The test surface is not the cost center.** 142 of 180 test files have zero
  a2kit contact. Real contact is ~75 call sites in 21 files, concentrated in ~10
  helpers. Estimated 1–1.5 focused days, dominated by six wire-test files whose
  a2kit contact is six ~8-line module helpers (the 1350 assertion lines never
  move).
- **The wire surface is two tools.** `refresh` is not advertised
  (`expose_cookies_tool` defaults false → `_A2WebServer` drops `CookiesRouter`),
  and `_meta.health` is disabled out of dispatch entirely.

**A green spike settles the hard part.** Against `fastmcp 3.4.4`: a router holding
memoized async thunks, tools taking only wire params, teardown on FastMCP's
`lifespan=`. All assertions pass — lazy-skip, lazy-entry + LIFO, dependency-safe
unwind, override, partial-entry safety, single-construction under 20 concurrent
calls. **27 non-blank lines of substrate.**

The decisive consequence: keeping the call shape `await browser_backend()`
identical to a2kit's `Lazy: TypeAlias = Callable[[], Awaitable[T]]` means
**`fetcher.py` and every phase change zero lines**. Only the seam moves — from a
declared tool param to `self.browser_backend`.

## What Changes

- **Delete the a2kit spine.** `a2kit.App`, `Router`, `provide()`, the container,
  `a2kit.run`, `a2kit.runtime.build`/`apply_selection`,
  `a2kit.packages.serve.serve_process`, `A2kitConfig`/`McpConfig`, and the
  `a2kit[code-mode]` extra. a2web composes on `fastmcp.FastMCP` directly.
- **Hand-wire one composition root**, absorbing `bootstrap_state`, with a local
  27-line `ResourceScope` (LIFO teardown, records only after a successful
  `__aenter__`) + `Lazy` (memoized async thunk under a construction lock).
  Enforced as the *only* composition root by an architecture test, mirroring
  a2kay.
- **Explicit tool signatures** (design decision D1). A thin FastMCP function whose
  signature **is** the wire contract, closing over the router's resource bundle.
  Replaces a2kit's implicit `has_provider`-based wire/DI partition.
- **Reproduce the two-piece error mechanism** (a2kay Spike 2, banked): a per-tool
  wrapper raising `ToolError(prose) from exc`, plus an outer middleware
  recovering the envelope from `__cause__`. A single catch-all middleware does
  **not** work — FastMCP masks plain exceptions before middleware sees them.
- **Logging → sync typed events** (design decision D3). a2kit's async `log.info`
  exists solely for an MCP-wire forward with zero consumers in a2web; ~27 sites
  drop their `await`. Port a2kit's `_IsolatingHandler` semantics, which a2web's
  own `OtelHandler`/`LiveSink` currently lack.
- **Vendor `encode_tsv` verbatim** during the migration so the wire is
  byte-identical; adopt `lean-wire` as a **separate, released change** (design
  decision D2).
- **Do NOT adopt `page-tsv` or `mcp-result-wire`** — see design D2.
- **Delete architecture tests that police dead idioms**, and fix one that would
  otherwise go vacuously green.

## Impact

- `src/a2web/server.py`, `routers.py`, `state.py`, `models.py` (2 import lines),
  `log.py`, `events/`, `cache.py`, `cookie_jar.py`, `llm_resource.py`.
- **`fetcher.py` and the phases: zero changes** (the `Lazy` call shape is
  preserved deliberately).
- ~21 test files; 2 architecture tests deleted, 1 hardened against vacuity.
- `pyproject.toml`: a2kit removed, `fastmcp` direct.
- **Wire contract: unchanged.** Gated by `wire-contract-golden-gate` at zero
  deltas.
- **Supersedes** `envelope-wire-hygiene` task 3.1 ("adopt the a2kit fix when
  shipped") — the migration deletes the offending middleware outright, so the fix
  arrives by deletion. That change's `xfail(strict=True)` tripwires must be
  un-xfailed here.

## Open questions — ALL FOUR ANSWERED (2026-07-22)

**Q1. The Typer CLI. → (a) KEEP, hand-written.** `a2kit.run(app)` generates a
full CLI from the same tool signatures: `a2web web query --url=…`, `a2web
health`, `a2web serve`. It is in the Makefile and the global install, and it is
how a2web is driven by hand. FastMCP's `generate-cli` is not a substitute — it
produces a *reconnecting client*, a different thing.

Design in **D6**. The short version: derive the Typer command from the FastMCP
tool function's signature, which D1 has already made unambiguous — a2kit's CLI
generation was opaque because of the *wire/injected partition guess*, not
because of the generation, and D1 deletes the guess. Vendor a2kit's 54-line
`_field_to_typer.py`; drop the framework meta-commands (`schema`, `list-tools`,
`code`, `_meta`).

**D6 also raises the phase's real risk: the CLI is a second wire contract and
it is entirely ungated** — 1236 tests, none of which invoke the CLI. Phase 5
must therefore begin with a CLI golden gate, not with the Typer app.

**Q2. The live log-notification stream. → KEEP.** Not marginal, as this question
assumed: the goldens show **fifteen frames per `query` call**, a live progress
feed for a call that can run tens of seconds. It is a product surface. Landed in
Phase 1.

**Q3. `typed-events` vs `scoped-log`. → a2web's own shape, and it stays ASYNC.**
The correlation surface is confirmed dead (`call_id`/`trace_id`/`tool_name` —
zero readers) and is not reproduced; `elapsed_ms` is dropped as redundant with
the events' own `t_ms`/`dur_ms`. But **the "sync" half of this answer was wrong
and the goldens disproved it**: given Q2, async is not optional, because the
wire forward is an inline `await ctx.log(...)` and a `logging.Handler` cannot
await. Emission is ~120 local lines in `src/a2web/log.py`; nothing was adopted
from the shelf. Landed in Phase 1.

**Q4. Strangler vs atomic. → STRANGLER, confirmed by execution.** Phases 1–3 are
landed independently and green, each gated on zero wire deltas (Phase 1 carrying
one characterized, documented delta). a2kit imports in `src/` went 16 → 7
without a single atomic commit. Phase 4 remains indivisible.
