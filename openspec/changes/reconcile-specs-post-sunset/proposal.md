## Why

`sunset-a2kit-dependency` retired a2kit in the **code** (composition on
`fastmcp.FastMCP` directly, envelope/wire owned in-tree) but never reconciled the
**specs**. Eleven of the main capability specs under `openspec/specs/` still
describe the a2kit world verbatim, and they now lie about the running system:

| spec | a2kit residue (sample) |
|---|---|
| `app-composition` (20 hits) | `a2kit.App` + `a2kit.run(app)`, `app.provide`, `EventBus`, `ToolContext`, `fit_md`/`tokens`, `canonical_name_override`, "survives a2kit substrate upgrades", a `fetch` tool that no longer exists |
| `streaming-progress` (8) | MCP progress sink + `ctx.event`/`ctx.report_progress` per phase — retired for stdlib-logging events |
| `app-logging` (7) | the `a2kit` logger / LDD wire path |
| `browser-cookies`, `ask-response`, `endpoint-auth`, `browser-tier`, `tier-pipeline`, `extraction`, `output-benchmark` | scattered `a2kit`/`app.provide` references |

The sunset change carried a *correct, already-written* set of FastMCP-direct
requirements for `app-composition` — but its delta was malformed (one requirement
labelled `MODIFIED` against a base that never had it, and no `REMOVED` block for
the a2kit-era requirements it replaces), so the archive could not apply it. The
sunset was archived `--skip-specs`; that delta is preserved in
`openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/` as source material
for this change.

This is the "**never treat a golden as proof**" hazard from CLAUDE.md, at the spec
layer: a spec that describes a dead substrate reads as coverage while providing
none. It is spec-only — no code changes, the code is already correct.

## What Changes

- **Rewrite `app-composition`** to the FastMCP-direct architecture: seed the
  ADDED requirements from the archived sunset delta (`build_mcp_server`, the one
  composition root, lazy first-use, LIFO teardown, explicit wire params, the
  substrate readiness probe, synchronous typed events), REMOVE the a2kit-era
  requirements they replace, and reconcile the framework-neutral survivors
  (closed-enum verdicts, YAML+env config) so their bodies stop naming a2kit.
- **Sweep the other 10 specs** for a2kit residue: each reference is either
  (a) rewritten to the current mechanism (stdlib-logging events, `plugin_surface`
  discovery, direct `fastmcp` wire) or (b) deleted if it described a retired
  feature. Every edit cites the current source module.
- **Add a residue guard** (task) so the debt cannot silently re-accrue: a test
  asserting no `openspec/specs/**` file contains `a2kit`/`app.provide`/`EventBus`
  outside an explicit historical-note allowlist — paired with a non-vacuous floor
  (CLAUDE.md: every structural guard asserts it found something).

## Impact

- **Spec-only.** No `src/` change. The witness that each rewritten requirement is
  true is the existing passing test suite + live server — not the spec itself.
- Unblocks a clean spec baseline for every future change; today an author reading
  `app-composition` would design against a2kit.
- Non-goal: re-deriving requirements from scratch. Where the sunset delta already
  wrote the FastMCP-world requirement, reuse it verbatim.
