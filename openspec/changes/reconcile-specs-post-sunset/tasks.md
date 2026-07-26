# Tasks

Spec-only reconciliation. The witness for every rewritten requirement is the
existing passing suite / live server, NOT the spec text. Cite the current source
module in each requirement body.

## 1. Anchor: app-composition (the worst offender, 20 hits)
- [x] 1.1 Copy the archived sunset delta's `## ADDED Requirements`
      (`archive/2026-07-26-sunset-a2kit-dependency/specs/app-composition/spec.md`)
      as the new baseline; move the mislabelled "Typed events…" from `MODIFIED` to
      `ADDED`. — done: `specs/app-composition/spec.md` seeded; verified the base
      spec has no "Typed events" requirement, so `ADDED` is correct.
- [x] 1.2 Author `## REMOVED Requirements` for the a2kit-era ones the new set
      replaces: "Public fetch tool envelope" (`fit_md`/`tokens`/`EventBus`),
      "Server composition entrypoint" (`a2kit.App`/`a2kit.run`), "CookieJarResource
      is registered via app.provide", "Canonical MCP tool names pinned under flat
      naming", "MCP wire contract survives a2kit substrate upgrades". — done: all
      five verified present in the base `app-composition` spec before removal.
- [ ] 1.3 Reconcile framework-neutral survivors so bodies stop naming a2kit:
      closed-enum verdicts/status, "Configuration via single YAML file plus env",
      cookies-refresh tool, OperatorHint docstring.
- [ ] 1.4 `openspec validate --change reconcile-specs-post-sunset` on the
      app-composition delta before moving on.

## 2. Sweep the remaining 10 specs
- [ ] 2.1 `streaming-progress` — rewrite to stdlib-logging typed events
      (`await a2web.log.info(...)`, `logging.Handler` sinks); drop the MCP
      progress-sink / `ctx.event` requirements (no consumer post-sunset).
- [ ] 2.2 `app-logging` — `a2kit` logger → the single `a2web` logger
      (`propagate=False` + NullHandler floor); LDD wire → wire-level forward.
- [ ] 2.3 `browser-cookies`, `ask-response`, `endpoint-auth`, `browser-tier`,
      `tier-pipeline`, `extraction`, `output-benchmark` — per-reference: rewrite to
      current mechanism (`plugin_surface`, direct `fastmcp`) OR delete if the
      feature retired. One commit-sized delta per spec.
- [ ] 2.4 `openspec validate` each delta.

## 3. Residue guard (non-vacuous)
- [ ] 3.1 Add `tests/architecture/test_no_a2kit_in_specs.py`: walk
      `openspec/specs/**`, fail on `a2kit`/`app.provide`/`EventBus`/`ToolContext`
      outside an explicit historical-note allowlist.
- [ ] 3.2 Assert the walk is non-vacuous (`minimum=` file floor, per
      `_walk.walked_files`) — a guard over zero files reads as coverage.

## 4. Close
- [ ] 4.1 `make check` green (the guard is the only new test; specs don't run).
- [ ] 4.2 `openspec archive reconcile-specs-post-sunset` — applies all 11 deltas
      to `openspec/specs/`.
