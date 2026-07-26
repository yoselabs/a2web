# Design — sunset a2web's a2kit dependency

The decomposition (what leaves and where it goes), the four load-bearing design
decisions, and the strangler order that keeps a2web green throughout.

Grounded in: a six-axis parallel analysis of a2kit's spine, wire, logging, test
surface, and substrate; a2kay's completed pilot (archived
`2026-07-16-sunset-a2kit-dependency`, including its two green spikes); and one new
green spike against `fastmcp 3.4.4` covering a2web's specific lazy-seam shape.

## Governing principle — inherit a2kay's answer, amend it where a2web differs

a2kay's verdict on DI was **DROP the container, hand-wire, the pattern IS the
answer**. That survives contact with a2web, with one amendment a2kay's design
could not cover: a2kay's `build_components()` is fully **eager** (it opens three
DuckDB handles at boot). a2web cannot be — a browser driver and an LLM provider
must not construct unless their code path fires. **The amendment: the router holds
`Lazy` thunks, not resources.**

Where a2kay said "maximize the shelf, keep the consumer thin", a2web's answer is
narrower — see D2 and D4. a2web is a thicker, more opinionated app with a real
product moat; not every substantial concern here is generic.

## The trisection — every a2kit part a2web touches

| a2kit part | verdict | where it goes |
|---|---|---|
| `App`, `Router`, `provide()`, `Container`, `runtime.build`, `apply_selection`, dispatch stages | **DELETE (spine)** | a2web composes on plain `fastmcp.FastMCP` |
| `packages/serve.serve_process`, transports, `code_mode`, `A2kitConfig`/`McpConfig` | **DELETE (FastMCP owns)** | FastMCP 3.x native |
| DI container + `Lazy[T]` | **DROP → KEEP-THIN** | 27 local lines: `ResourceScope` + `Lazy`. Not shelf substrate — a container is the spine ADR 0032 removes |
| `signature.wire_input_params` (the implicit wire/DI partition) | **DELETE** | explicit tool signatures — D1 |
| `packages/formatter` `PruneEmpty` + `encode_tsv` | **VENDOR now, `lean-wire` later** | D2 |
| `packages/formatter` `encode_envelope` / format-routing middleware | **DELETE — do not reproduce** | D2. Deleting it *is* the `envelope-wire-hygiene` fix |
| `log/emission` typed events (async) | **SHELF (`typed-events`), SYNC** | D3 |
| `_IsolatingHandler` semantics | **PORT** | a2web's own handlers lack it — D3 |
| `HealthResult` / `health_check` | **KEEP-THIN** | `await components.sqlite()` — more explicit than the container's implicit entry |
| `ToolError` envelope | **REPRODUCE (two-piece)** | a2kay Spike 2 mechanism |
| `a2kit.testing` (`client`/`peek`/`lazy`/`app_of`) | **DELETE**, except `lazy` → **REPATRIATE** | D4 |
| Typer CLI (`a2kit.run`) | **KEEP — Q1 answered (a)** | hand-write over the same bodies — D6 |
| `a2kit.lint` | out of scope | dev tool; decide separately |

## D1 — Explicit tool signatures (the hardest thing, and the right answer)

**The problem.** a2kit partitions tool params into wire vs injected by an
*implicit, ambient* rule: `wire_input_params` (`a2kit/signature.py:114-147`) drops
a param if `container.has_provider(hint)` or if it is `Lazy[...]`. There is **no
marker**. `state: AppState` is injected purely because `app.provide(build_state)`
registered that key. One classification simultaneously drives the MCP
`inputSchema`, the Typer CLI flags, `ToolDescriptor.wire_param_names`, and
dispatch injection — and it is re-derived in four places, plus a fifth divergent
implementation for the FastAPI surface that has no `Lazy` case at all.

Corollary worth stating plainly: **registering a provider for `str` would silently
swallow every `url` param on every tool.**

**Two honest replacements:**

| | Approach | Assessment |
|---|---|---|
| (a) | Reproduce `install_mcp_signature` — build a new `inspect.Signature` of wire params only, set `__signature__`/`__annotations__` on a wrapper | ~30 lines, byte-identical, but **carries forward the exact opacity that makes this hard to reason about** |
| (b) | **Split the tool** — a thin FastMCP function whose signature *is* the wire contract, closing over the router's resource bundle, calling the existing body | ~40 lines for both tools. The contract becomes a **literal property of the source** rather than a derived one. Kills the `str`-provider hazard |

**Decision: (b).** It is the same move a2kay's Spike 2 proved (injected deps
absent from the wire schema, `type` alias surviving natively), adapted to a2web's
seam. The cost is one hand-written parameter list per tool; the gain is that the
frozen `tool_schemas` contract is readable in the source instead of emergent from
a registry.

## D2 — Wire encoding: vendor now, `lean-wire` later, and reject two packages

**Adopt `lean-wire` — but NOT during the migration.** Its `PruneEmpty` is
character-identical to a2kit's (`models.py:18` is a true drop-in), but its
`encode_tsv` deliberately **changes the bytes**: it replaces
`csv.DictWriter(QUOTE_MINIMAL)` with raw join + per-cell escaping of `\ \t \n \r`.
Measured divergence on real rows:

| cell contains | a2kit today | `lean-wire` | differs |
|---|---|---|---|
| `the "Downloads" page` | `"the ""Downloads"" page"` | `the "Downloads" page` | **YES** |
| `line1\nline2` | quoted, embedded newline | `line1\nline2` | **YES** |
| `a\tb` | quoted | `a\tb` | **YES** |
| `C:\path` | `C:\path` | `C:\\path` | **YES** |
| plain ASCII | identical | identical | no |

The `"` case is the most likely to fire — LLM-authored `OtherPage.reason` prose
contains quotation marks routinely. And a2web **does** emit interior newlines
today: `content_extract` does an outer `.strip()` only, so multi-line `<a>` markup
(title + price + rating in one anchor — ubiquitous on commerce and aggregator
pages) carries `\n` straight into `Link.anchor` → `_links_tsv`. That is precisely
the row-tearing bug `lean-wire` fixes.

**Therefore: two independent wire deltas must not land in one commit.**
- *Migration:* vendor a2kit's `tsv.py` verbatim as `a2web/_tsv_compat.py`.
  Goldens must be **byte-identical**; any diff is a regression.
- *Separate change:* swap to `lean_wire.encode_tsv`, re-bless under the
  `lean-wire-escaping` slug, record the delta. `lean-wire`'s own contract is that
  **semver is the wire-format version**.

**Reject `page-tsv`.** a2web never uses `Page`, never uses `format_response`
outside a2kit's test client, and hand-rolls all envelope shaping in `_prune_wire`.
The only reason a2kit's inference touched a2web was to auto-derive the `envelope`
plan — the thing being deleted. Adopting `page-tsv` re-imports the problem.

**Reject `mcp-result-wire` — actively harmful.** Its `_format_routing` *is* the
a2kit middleware that today resurrects empty conditionals and destroys populated
`other_pages`. Its entire net effect on a2web is that defect. **Dropping it is the
fix**; let plain FastMCP's `pydantic_core.to_json` serialize a2web's
already-shaped model.

## D3 — Logging: sync, and wider than a shim

a2kit's async `log.info` is async for **exactly one reason**: a 6-line MCP-wire
forward (`emission.py:89-97`). The stdlib half is synchronous and always fires.
Nothing in a2web consumes the forward — no test, no product doc, no client
behavior. a2web has **already re-implemented the sync half twice**
(`src/a2web/log.py`, whose docstring says so outright, and inline in
`wobble/_internal.py`).

**Decision: the API is sync.** ~27 sites drop `await`. This also makes the shelf
package trivially fastmcp-free.

**The package must be wider than a 50-line typed-instance→LogRecord shim**, which
would not pass DEEP. The bundle that does hides three real stdlib traps:

1. **Reserved-name-safe `extra`** — stdlib `extra=` raises `KeyError` on reserved
   `LogRecord` names, hence the single-dict convention.
2. **A handler that can never kill its producer** — a2kit's `_IsolatingHandler`
   catches, reroutes failures to a non-propagating logger, and drops the record.
   **a2web's own `OtelHandler` and `LiveSink` lack this**, so post-migration an
   OTel exporter hiccup would propagate into the fetch path.
3. **OTel-span-per-`*Ended`** — already duplicated across a2kit and a2web; rule of
   three is met.

Incidental fix: a2web currently emits **double OTel spans** (a2kit's
`otel_sink="auto"` plus a2web's own manifest handler). Migration removes one.

Renames required: logger `"a2kit"` → `"a2web"` (~8 sites), record attribute
`a2kit_fields` → `fields` (~12 sites incl. tests).

**Open (Q3):** this is narrower and sync-er than the shelf backlog's `scoped-log`
spec. a2web is the pilot (a2kay uses plain `logging`), so a2web's shape should
win — needs confirmation and a backlog edit.

## D4 — Tests: repatriate one function, delete the rest, pay full price on six files

- **`lazy` is 3 lines and is already a2web's own seam** (`Lazy[T]` is consumed at
  `fetcher.py:27`, `routers.py:22`, `state.py:26`). Export it from a2web; **49
  call sites go zero-diff.** This is repatriation, not shimming a dead idiom.
- **Do NOT shim `client` / `call_wire` / `peek` / `app_of` / `has_provider` /
  `container()`.** `peek`/`app_of`/`has_provider` have no FastMCP counterpart —
  shimming them means keeping a container alive purely to satisfy tests, which is
  exactly the "wrap the new shape back into the old one" failure the shelf loop
  names. Deletion is *cheaper* than the shim. `client()` is 90% dead weight for
  a2web (zero uses of `invoke`, `events`, `logs`, `progress`, `render_as`).
- **`call_wire` is the honest one** — its content is
  `format_response(sc, format_hint=…)`. A shim there would silently pin a2web to
  a2kit's formatter forever, disguised as test infrastructure, and hide the D2
  decision. The six wire files absorb the semantic change.

**Delete outright:**
- `tests/architecture/test_no_lambdas_in_app_provide.py` — its subject
  (`app.provide`) ceases to exist; it would be permanently vacuous green. (Also
  noted: the rule was stricter than a2kit itself, which uses a lambda internally,
  and a2web's own tests violate it 6× — legal only because the AST scan is scoped
  to `src/`.)
- `tests/architecture/test_no_ldd_terminology.py` — bans the branding of a
  subsystem already removed from a framework now being removed. Double-dead.
- The four DI-container assertions in `tests/capabilities/app_state/test_app_state.py`
  (`_build_probe_app`, `test_provider_registered`, `test_peek_returns_resolved_state`,
  `test_two_apps_have_independent_states`) — they assert a2kit's container caches
  singletons per-App. a2kit's own test, wrongly living in a2web.

**Harden, do not delete — the vacuity trap:**
`tests/architecture/test_tools_return_pydantic_not_str.py` matches decorators via
`isinstance(dec.value, ast.Name) and dec.value.id == "a2kit"`. After the move to
`@mcp.tool` it **does not fail — it inspects zero functions and stays green
forever.** Retarget the matcher AND add `assert len(inspected) >= 2`. Audit every
other AST-walking architecture test for the same pattern.

**Keep, rationale-rewrite only:** `test_aiosqlite_daemon.py` (an aiosqlite+pytest
fact, zero a2kit dependency), `test_response_models_at_module_scope.py` (the real
reason is FastMCP schema generation, which *survives* — the rule becomes more
load-bearing), `test_no_rogue_structlog.py` (the invariant is "no stdout, which
corrupts MCP stdio" — a product invariant, not an a2kit one).

## D5 — What disappears for free

- **`RobustBrowserBackend`** (`state.py:52-62`) — a marker Protocol that "adds
  nothing", existing *solely* because a2kit resolves by type key and two
  `BrowserBackend` providers would collide. Hand-wiring makes it two variables;
  the type is deleted.
- **The `Never call _ensure() in a health_check body` rule** — it exists only
  because the container made resource entry implicit. Hand-wired, the health
  check is `await components.sqlite()`, which is explicit and needs no rule.
- **`code_mode` config + the `a2kit[code-mode]` extra.**
- **One of the two OTel span emissions.**

## D6 — The CLI: keep it, and derive it from the one signature D1 creates

**Q1 answered (2026-07-22): keep the CLI** — option (a). It is in the Makefile,
in the global install, and it is how a2web is driven by hand.

### What is actually on the surface today

```
a2web
├── serve          ← the global MCP install + `make dev` use this
├── health         ← container readiness probe
├── web query      ← the product CLI
├── web fetch_raw
├── cookies refresh   (only when expose_cookies_tool)
├── schema         ─┐
├── list-tools      ├─ a2kit framework artifacts, not a2web product
├── code            │  (`code` dies with code-mode in task 4.8 regardless)
└── _meta          ─┘
```

**The CLI output contract, which nothing in this repo has ever written down:**
`format_response(result, format_hint="auto")` → `infer_format_hint` returns
`json` for both `AskResponse` and `FetchResponse` → **compact JSON**
(`separators=(",", ":")`), then `truncate(..., max_chars=50_000)` appending
`"... (truncated)"`. Verified by running it:

```
$ a2web web fetch_raw --url=https://example.com
{"url":"https://example.com/","tier":"browser","confidence":"low","content_md":"…"}
```

### The finding that should govern this phase

**The CLI is a second wire contract, and it is completely ungated.** 1236 tests,
and not one of them invokes the CLI — no `CliRunner`, no subprocess, nothing.
Every byte above (the compact separators, the 50k cap, the truncation marker,
the command tree, the flag names) is inherited behaviour that no test asserts
and no doc records.

This is the same shape as the notification-payload gap found in Phase 1, and it
is larger. Phase 1 got lucky: the notification stream *happened* to be captured,
badly, and widening it before touching anything caught both a wire change and a
latent flake. There is no equivalent luck available here — the capture does not
exist at all.

**So Phase 5 must not start with the Typer app. It must start with a CLI golden
gate**, mirroring `tests/contracts/wire/`: drive the real CLI with stubbed tiers
and freeze stdout/stderr/exit-code per command. Without it, "hand-write a small
Typer app" is an unverifiable rewrite of a surface the user drives daily.

### How to write it: derive from the D1 signature

The obvious objection to a hand-written CLI is duplication — a parameter list
for FastMCP *and* a parameter list for Typer, free to drift apart. Three ways
out:

| | Approach | Assessment |
|---|---|---|
| (a) | Two hand-written signatures over one body | Explicit, ~30 extra lines, but the CLI flags and the MCP schema can silently diverge — and only the MCP half is gated |
| (b) | One pydantic params model; FastMCP takes explicit fields, Typer derives flags from the model | No drift, but adds an indirection D1 just finished removing |
| (c) | **Derive the Typer command from the FastMCP tool function's `inspect.signature`** | ~40 lines. One signature, no drift, no new indirection |

**Decision: (c), and D1 is what makes it safe.**

a2kit derived its CLI the same way, and that derivation was the single most
opaque thing in the framework — but *not because deriving a CLI from a signature
is bad*. It was opaque because `wire_input_params` had to **guess** which
parameters were wire and which were injected (`container.has_provider(hint)` or
`Lazy[...]`, no marker, re-derived in five places, and a `str` provider would
have swallowed every `url`).

After D1, the FastMCP tool function's signature contains **only** wire
parameters — that is the entire point of D1. So the guess disappears, and
signature → CLI flags becomes a pure total function over an unambiguous input.
The dangerous half of a2kit's CLI generation was the partition, not the
generation. We keep the generation and delete the partition.

Concretely, one piece of a2kit is worth vendoring nearly verbatim:
`packages/cli/_field_to_typer.py` — 54 lines rewriting
`Annotated[T, pydantic.FieldInfo]` → `Annotated[T, typer.Option(help=…)]`.
a2web's tool params are already written that way, so the descriptions the MCP
schema publishes become the `--help` text for free. The other 635 lines of
a2kit's `builder.py` are router-tree walking and meta commands we are dropping.

### Decisions to make explicit rather than inherit

1. **Drop `schema` / `list-tools` / `code` / `_meta`.** Framework
   introspection, not product. `code` is already slated for deletion with
   code-mode (4.8). Keep `serve`, `health`, `web query`, `web fetch_raw`,
   `cookies refresh`.
2. **The 50k truncation + `"... (truncated)"` marker** is inherited and
   undocumented. On `web query` it is nearly unreachable (the envelope is lean
   by construction); on `fetch_raw --include-content` it is very reachable.
   Recommend: keep the cap, but only after the golden records the current
   behaviour, so the choice is visible rather than accidental.
3. **Per-command lifecycle stays.** a2kit's CLI entered and exited the whole
   runtime per command — opening and closing sqlite on every `a2web web query`.
   For a CLI that is *correct*, not wasteful: a one-shot process should not
   leave a database handle to chance. Confirm teardown still runs (task 5.3).

## The honest risk, and its mitigation

a2web's `Never bypass Lazy[T] at the tool seam` rule and the `no globals / no
module-level lazy caches` convention were **free because the framework owned
resolution**. Hand-wiring makes them discipline again: nothing structurally stops
a future contributor from `await self.browser_backend()` at the top of `query()`
and silently killing cold start.

**Mitigation — a hard task, not a nice-to-have:** promote the spike's R1 assertion
into `tests/architecture/` — a cold-start test asserting that a `query` served
from cache or the raw tier leaves the browser and LLM thunks **unresolved**. That
converts the convention back into a structural guarantee. Plus the a2kay-style
"one composition root" architecture test.

## Rejected alternatives

- **Adopt `svcs`.** Tested hands-on, not judged from docs. Two defects: (i) unwind
  is **not dependency-safe** for nested factories (`aget` appends to `_on_close`
  before `__aenter__`, so a factory resolving a dep inside its own entry is torn
  down last); (ii) **no partial-entry safety** — a resource whose `__aenter__`
  raises still gets `__aexit__` called, the exact MCP-SDK #1213 hazard a2kit's
  `CleanupStack` was written to avoid. It also has no type-directed factory param
  injection, so every a2web factory would become a service-locator body. Fails
  DEEP (one scope, ten providers), fails WINS (27 lines), fails correctness.
- **FastMCP's native `fastmcp.server.dependencies`.** It exists on 3.4.4 and
  correctly hides injected params from the wire schema — but it is **per-call
  scoped** (fresh `AsyncExitStack` and cache per invocation), so used naively for
  the browser pool it relaunches Chromium on every fetch. It is also not public
  API (a re-export of `docket`'s `_Depends`). Fails STABLE.
- **`dishka` / `that-depends` / `dependency-injector`.** Maintained and capable,
  but heavyweight FastAPI-shaped containers — i.e. the spine ADR 0032 removes.
- **Promoting `Lazy`/`ResourceScope` to the shelf.** 27 lines with a2web-specific
  `ResourceUnavailable` degradation semantics. DUPLICATE, not PROMOTE.
- **No BENCH.** The build-vs-adopt question is settled by *correctness*, not
  performance: the leading adopt candidate fails two behavioural assertions the
  27-line version passes. There is nothing left to measure.

## Documentation debt found while scoping (fix in this change)

`CLAUDE.md` has drifted and will mislead the migration:
- says eight `provide` registrations; there are **ten**.
- names `browser_pool` / `BrowserPool`; the keys are now `BrowserBackend`,
  `RobustBrowserBackend`, `Provider`.
- claims resolution is *"insertion order, not topological"* — it is **neither**.
  It is demand-driven recursive DFS; registration order is irrelevant to
  correctness, and `server.py:101`'s *"Order matters: deps before dependents"*
  comment is simply false.
- documents the error envelope as `{class, message, traceback}`; the real shape is
  a2effect's `ErrorEnvelope{type, kind, base_kind, retryable, hint, details,
  cause}` and there is no `traceback` key anywhere.

## Q2 / Q3 / Q4 — answered by execution (2026-07-22)

Task 0.1 asked for these to be resolved before starting. They were instead
resolved *by* the phases, which is worth recording honestly rather than
back-dating: each answer is what the work turned out to require, and two of
them differ from what the question anticipated.

**Q2 — log notifications: KEPT, unchanged in shape.** The MCP-wire forward is
still gated on being inside a tool dispatch; the synchronous log to the `a2web`
logger always fires. No a2web code needed to change, because Phase 1 had
already moved the emit sites to `await a2web.log.*` and the notification
payload gate in `tests/contracts/wire/notifications.json` covers the forward.
The migration's only notification-visible change was dropping `_meta.a2kit`,
recorded as the `a2kit-spine-removed` delta.

**Q3 — `typed-events` vs `scoped-log`: a2web's shape wins, and it is no longer
a shelf question.** The premise was that a2web is the pilot for a shelf
`scoped-log` package. What Phase 1 actually produced is ~40 lines of `a2web/log`
over stdlib `logging` with no reusable core: the three items listed above as
promotable are reserved-name-safe `extra`, a non-fatal handler, and
span-per-`*Ended`. The first is two lines, the second is a stdlib idiom, and the
third is OTel glue that belongs with an OTel package. Per the shelf's own ADOPT
gate (DEEP · STABLE · WINS) this is a shallow candidate — a boundary with
nothing behind it. **Recommendation: drop `scoped-log` from the shelf backlog**
rather than promote a2web's version. Not actioned here; it is a shelf edit, and
`shelf-sweep-promotions` owns the verdict table.

**Q4 — strangler vs atomic: BOTH, split on a seam the question did not have.**
The question assumed one answer for the whole migration. The phases proved the
split is per-concern, and the boundary is *whether the concern has a seam*:

| | Concern | Shape | Why |
|---|---|---|---|
| Strangler | logging (1), TSV codec (2), `Lazy` (3) | landed independently, green between each | each had a seam a2web already owned, so the old and new could coexist |
| Atomic | the spine (4) | one commit, 51 files, −1046 lines | `App` + container + wire + error envelope resolve each other; removing any one alone leaves the others unable to construct |
| Gated rewrite | the CLI (5) | capture-then-rewrite | not a strangler (no seam to run both) and not safely atomic (ungated surface) — so the golden gate substituted for the safety a seam would have given |

The third row is the one worth keeping. When a surface is neither strangleable
nor safely atomic, **freezing its observable behaviour first is the third
option**, and it is cheaper than it looks: the Phase 5 capture took one
afternoon and immediately found a 404'd container healthcheck, a no-op flag, a
dead truncation cap, and a typo shipped to every agent for months.
