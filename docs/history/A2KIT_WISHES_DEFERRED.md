# a2kit — deferred wishes (consolidated open-items list)

Status: parked, not abandoned. None of these block a2web. This is the single
open-items list the next a2kit feedback round starts from.

Last consolidated: 2026-05-22, after `generic-record-extraction`. This pass
merged the scattered carry-over notes from rounds 11–12 (`A2KIT_FEEDBACK_v0.40.md`,
`v0.41.md`) into this file and retired three superseded entries (see bottom).

Current baseline: a2kit v0.39.3.

---

## 1. Formatter-level empty-field omission (`exclude_none` / `exclude_defaults`)

**Context.** `a2kit.packages.formatter` serializes every tool return with a
plain `model_dump(mode="json")` — every optional field reaches the wire even
when empty (`byline: null`, `meta: {}`, `next_links: []`). On a token-sensitive
tool like `ask` that is pure noise.

**Ask.** Let a return type opt into pruning empty fields (`None`/`[]`/`{}`/`""`)
from the JSON payload — a per-return-type formatter option, or a model-level
marker honored by `format_response`.

**Status.** Filed round 12 (v0.41). a2web ships a per-model
`@model_serializer(mode="wrap")` workaround (`AskResponse` / `FetchResponse`'s
`_prune_wire`); once a2kit absorbs this, a2web deletes the custom serializer.
Additive — default behavior unchanged.

## 2. LDD severity levels

**Context.** a2web emits routine events (`CookiesAttached`, `TierStarted`)
and operator-actionable warnings (`CookiesStale`) through the same channel at
the same volume. Operators can enable everything or nothing.

**Ask.** A `level: Literal["trace","debug","info","warn","error"]` on LDD
event payloads (or an `emit(level=...)` arg) plus a sink-side filter:
`app.ldd.add_sink(otel_sink, min_level="warn")`. Default `info`; existing
sinks default to no filtering. Additive, no wire-format break.

**Status.** Filed round 11 (v0.40). Levels need to live on the LDD bus, not
structlog — the bus is what bridges to MCP progress / OTel spans.

## 3. Per-tool runtime selection at server start

**Context.** a2web ships an `ask_only: bool` setting + a constructor-time
`WebRouter.tools` rebuild to expose a tool subset. Every a2kit app that wants
this discipline (a2db read-only, a2atlassian no-write) reinvents the boolean.

**Ask.** A first-class runtime tool-subset selector — env var / CLI flag —
intercepted before `build_mcp_server(app)`: `a2web serve --tools=ask`.
Complements the compile-time `visibility=` decorator kwarg. Additive (no flag
= expose all).

**Status.** Filed round 11 (v0.40). Once shipped, a2web deletes `ask_only`.

## 4. Canonical-surface promotion — `a2kit.Lazy`, `a2kit.LddEmission`

**Context.** `Lazy` — the most-touched DI primitive at the tool seam — still
lives at `a2kit.packages.di.Lazy`; `LddEmission` (sink-author surface) at
`a2kit.packages.ldd.LddEmission`. `a2kit.packages.*` reads as internal
scaffolding.

**Ask.** Promote both to top-level re-exports (`a2kit.Lazy`, `a2kit.LddEmission`)
alongside `a2kit.App` / `Router` / `ToolContext` / `HealthResult`. Document
`a2kit.packages.*` as private (stdlib `_thread` / `threading` convention).

**Status.** Round 10 Friction C; restated round 11. `a2kit.testing.*` already
became canonical — partial win. Cosmetic / discoverability, not blocking.

## 5. `a2kit.desc` — `pydantic.Field` description sugar

**Context.** `routers.py` is 60–70% `Annotated[T, pydantic.Field(description="...")]`
ceremony — each tool param spans 8–12 lines.

**Ask.** Sugar — `a2kit.desc("…")` expanding to `pydantic.Field(description=…)`,
or `a2kit.param(description=…, default=…)` for the combo. Not a new primitive
(`a2kit.Param` was correctly retired) — just shaves the wrap.

**Status.** Round 10 Friction D; restated round 11. Lowest-priority polish.

## 6. `@a2kit.read(timeout="60s")` decorator kwarg

**Context.** Every network-facing tool wraps its body in
`async with anyio.fail_after(...)`. `OPERATIONAL_CONTRACTS` Q2 documents this
as the contract, but it is repetitive.

**Ask.** `@a2kit.read(..., timeout="60s")` — dispatcher wraps the body;
`timeout=None` keeps current behavior; the configured value surfaces in tool
annotations so agents can set retry policy.

**Status.** Round 3. Ergonomic, not load-bearing. Bundle into a decorator-polish
round.

## 7. Decorator-time enforcement of `tools`-tuple completeness

**Context.** A `@a2kit.read`-decorated Router method that is omitted from the
`tools` tuple silently does NOT register — no error, invisible on every
transport. v0.31's CHANGELOG promised a follow-up lint rule; not yet shipped.

**Ask.** Ship the static lint rule (preferred — lint-time, no runtime cost),
OR raise at `Router.__init__` when a class callable has `_a2kit` meta but is
absent from `tools`.

**Status.** Round 7. Still open per round-10 Friction G. a2web has one tool so
the drift is easy to catch manually — raise priority when a second tool lands.

## 8. Streaming response API

**Context.** `FetchResponse.content_md` can be 100 KB+; the calling agent
waits for the whole body before any of it is visible. MCP supports chunked
responses for exactly this.

**Ask.** `@a2kit.read(streaming=True)` with either an `AsyncIterator[Chunk]`
return or an explicit `await ctx.chunk(...)` emit + terminal return.

**Status.** Round 3. Parked — no downstream caller has reported long-article
latency. Reopens on a real latency complaint or a streaming "fetch + extract"
tool.

## 9. `make ty` escape hatch for unresolvable third-party modules — NEW (2026-05-22)

**Context.** Surfaced in `generic-record-extraction`. `import lxml.etree`
makes `make ty` fail with `unresolved-import` — `ty` has no stubs for
`lxml.etree` (it resolves `lxml.html` but not `lxml.etree`). a2kit owns the
`make ty` toolchain and exposes no documented way to ignore a per-module
resolution failure on a third-party package. The workaround was to **distort
the code** — avoid `import lxml.etree`, catch builtin exception types
(`ValueError`, `SyntaxError`) instead of the precise `lxml.etree.ParserError`.

**Ask.** A documented escape hatch in a2kit's `ty` config — a per-module
ignore / "treat as Unknown" passthrough, or a sanctioned inline-suppression
form — so a third-party stub gap doesn't force a code workaround.

**Status.** New, low priority. `ty` is pre-1.0 (Astral); stub coverage will
improve. a2kit just needs to not make a stub gap unworkaroundable.

## 10. `Lazy[T]` introspection helpers

**Context.** Named as a carry-over wish in rounds 11–12 but never given a
detailed filing. The intent: inspect a `Lazy[T]` handle — is it already
resolved, what type does it wrap — without forcing resolution.

**Status.** Needs a proper filing with a concrete use case before it can be
acted on. Placeholder so it is not lost.

## 11. `app.tools()` name-override mechanism

**Context.** Named as a carry-over wish in rounds 11–12 but never given a
detailed filing. The intent: override / alias a tool's wire name without
renaming the Router method.

**Status.** Needs a proper filing with a concrete use case before it can be
acted on. Placeholder so it is not lost.

---

## Recently retired (this consolidation, 2026-05-22)

Three entries from the prior version of this file were removed as superseded —
recorded here for trace:

- **`app.singleton(..., teardown=fn)`** — `app.singleton` was retired in
  a2kit v0.36; lifecycle is now `app.provide` + `__aenter__` / `__aexit__`
  (LIFO unwind). The teardown concern no longer exists. (Closed per round-10
  Friction G.)
- **`_LDD_STATE` / `ctx=None` error-message refinement** — v0.39 binds
  ambient ctx unconditionally; a tool that does not declare `ctx` can still
  call `a2kit.ldd.event(...)`. The failure mode the wish addressed is gone.
- **Watch list — `align-context-method-signatures` /
  `rebuild-test-client-on-real-context`** — a v0.28-era tracking note; the
  v0.32→v0.39 migrations are long shipped and audited clean.

## How to retire an entry

When one ships in a2kit or stops mattering for a2web:

1. Move it to `docs/history/A2KIT_FEEDBACK_v<version>.md` with a one-line
   "shipped / dropped / superseded by X" note (or list it under "Recently
   retired" here on the next consolidation pass).
2. Delete the entry from this file.

Keeps this file lean and current.
