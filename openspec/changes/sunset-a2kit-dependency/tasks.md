# Tasks

> **Prerequisites: BOTH SATISFIED (2026-07-22).**
>
> `hotfix-fastmcp-error-envelope` landed (fastmcp `>=3.4,<4`, error envelope
> repaired). **`wire-contract-golden-gate` is ARMED** — 11 goldens under
> `tests/contracts/wire/`, captured through a real `fastmcp.Client` against the
> real `build_mcp_server(build_app())`, on the post-hotfix build.
>
> **The gate for every phase below is ZERO DELTAS.** Run:
>
> ```sh
> uv run pytest tests/contracts/test_wire_contract.py
> ```
>
> Any diff is a regression until proven otherwise; proving otherwise means
> accepting it with `A2WEB_ACCEPT_WIRE_DELTA=<slug>` and writing the reason into
> `tests/contracts/DELTAS.md`. There is deliberately no blanket bless. This is
> what makes the sunset landable as a *sequence* instead of one unverifiable
> commit.
>
> Two tripwires will flip during this work and MUST be un-xfailed, not
> re-marked:
> - `tests/contracts/test_wire_contract.py::test_populated_other_pages_survives_to_text_channel`
> - the two in `tests/capabilities/ask_response/test_envelope_dispatch_encoder.py`
>
> All three are `xfail(strict=True)`, so deleting the offending middleware turns
> them into hard failures automatically. That is the design: the fix cannot land
> silently.
>
> One more standing check to keep in mind: `test_framework_matches_the_resolved_mcp_substrate`
> AST-walks a2kit for FastMCP API drift. When a2kit goes, either retire it or
> re-aim it at a2web's own FastMCP call sites — which is where the drift risk
> moves.
>
> **Blocked on human decisions Q1–Q4 in `proposal.md`.** Q1 (the Typer CLI) gates
> Phase 5 entirely and changes the size of this program more than anything else.

## 0. Decisions and prep

- [ ] 0.1 Resolve Q1 (Typer CLI: hand-write / drop / serve-only), Q2 (log
      notifications), Q3 (`typed-events` vs `scoped-log` shape), Q4 (strangler vs
      atomic). Record each in `design.md`.
- [ ] 0.2 Fix the `CLAUDE.md` drift enumerated in `design.md` (ten providers, the
      current DI keys, the false resolution-order claim + the false
      `server.py:101` comment, the stale error-envelope shape).
- [ ] 0.3 Confirm the shelf's `work/a2kay` branch is merged to `main` — four
      tagged packages (`lean-wire`, `page-tsv`, `mcp-result-wire`, `a2effect`)
      are stranded off `main`, so `lean-wire` cannot be cleanly pinned until it
      lands. Blocks the follow-on `lean-wire` change, not this one.

## 1. Logging → a2web-owned typed events — **DONE 2026-07-22**

> **Q2 and Q3 resolved, and Q3 resolved AGAINST the plan.** This phase was
> written as "logging → **sync** typed events", on the premise that a2kit's
> async emission surface was framework ceremony. It is not. The wire goldens
> captured in `wire-contract-golden-gate` show **fifteen `notifications/message`
> frames streaming per `query` call** — a live progress feed for a call that can
> run tens of seconds. That forward is an inline `await ctx.log(...)`.
>
> - **Q2 — keep the log notifications.** They are a product surface, not
>   telemetry exhaust. An agent watching a slow fetch sees tier escalation and
>   extraction happen.
> - **Q3 — keep the typed-instance→`LogRecord` shape, and keep emission
>   `async`.** Given Q2, sync emission is not available: a sync emitter cannot
>   await, and a `logging.Handler` that schedules the forward as a task loses
>   ordering and can outlive the call scope it belongs to.
>
> The gate is what produced this correction. Without the notification capture,
> the phase would have been executed as written and the stream would have
> degraded silently — the exact failure mode the goldens exist to prevent, on
> the first phase they were applied to.

- [x] 1.1 `src/a2web/log.py` is now the whole surface: async `info/debug/
      warning/error` (typed instance or string) + the sync `log_*` half + the
      `IsolatingHandler` base + `configure()`/`add_handler()`. ~120 lines of
      code. The MCP context resolves through
      `fastmcp.server.dependencies.get_context()`, so a2web needs no call scope
      of its own — one whole a2kit concept dropped rather than reimplemented.
- [x] 1.2 `IsolatingHandler` ported and **applied**: `events/sinks.OtelHandler`
      and `llm_eval/live_sink.LiveSink` both subclass it now. Two tests pin the
      contract — a raising sink does not reach the producer, and does not starve
      its sibling sinks.
- [x] 1.3 All 27 `await a2kit.log.*` sites migrated (kept `await`, per Q3).
- [x] 1.4 **Resolved as designed, not as planned.** The sync helper folded into
      the one module. The package-side emitters in `llm_extract/extractor.py`,
      `llm_extract/wobble/_internal.py` and `browser_backends/playwright.py`
      stay inline *deliberately*: `packages/` may not import `a2web.<domain>`
      (tach.toml), and referring to the logger by NAME is the smallest possible
      coupling to the host app. Their record shape is identical, so the same
      sinks drain them. Comments corrected — they claimed a2kit's `LogConfig`
      governed them, which is no longer true of anything.
- [x] 1.5 Logger `"a2kit"` → `"a2web"`, record attribute `a2kit_fields` →
      `fields`, everywhere in `src/` and `tests/`.
- [x] 1.6 **The double emission was real, and worse than recorded.** Two
      independent causes: (a) a2kit attaches its own generic `OtelHandler` at
      boot (`otel_sink="auto"`) — dissolved structurally, since a2kit's handler
      sits on the `a2kit` logger and never sees a2web records now; (b) **found
      while testing**: `build_app()` attaches the manifest sinks to a
      *process-wide* logger on every call, so the Nth build gave every `*Ended`
      event N spans. `add_handler` now replaces same-type sinks by default. This
      only surfaced because the single-span test was run in the FULL suite —
      it passed in isolation. Silent telemetry multiplication: traces look
      plausible, they are just wrong.
- [x] 1.7 `LogConfig` replaced by three `AppSettings` fields (`log_enabled`,
      `log_level`, `log_wire_level`) + `a2web_log.configure(...)` in
      `build_app()`. Three, not two: the MCP wire is the one channel that is not
      a stdlib handler and so cannot self-filter. a2kit's other six `LogConfig`
      fields had nothing to configure here — a2web attaches exactly one sink and
      owns no stream of its own.
- [x] 1.8 `ambient_for_tests_autouse` dropped from `tests/conftest.py`.
- [x] 1.9 `make check` green — **1236 passed, 3 xfailed, coverage 90.45%**
      (was 1223 / 90.44%: +13 tests). Verified order-independent across four
      randomized seeds.

- [x] 1.10 **`propagate = False` + a NullHandler floor, added beyond plan.** Not
      tidiness: a2web serves MCP over **stdio**, so a record escaping to the
      root logger's default stderr writer can interleave with the JSON-RPC
      stream, and a logger with no handlers at all falls back to
      `logging.lastResort` — which writes to stderr. Both are now pinned by
      test. The fallout was that three `caplog`-based tests broke, because
      `caplog` captures via the ROOT logger: they had been passing on
      propagation production must not have, and they were order-dependent
      (passing alone, failing in a suite, depending on whether `build_app()` had
      run yet). They now attach directly via a new
      `tests/_helpers/log_capture.capture_log_records()`.

- [x] 1.11 Wire goldens: **one accepted delta**, slug `a2web-owned-log-emitter`.
      Across all fifteen frames the only change is the removal of
      `a2kit_elapsed_ms` — same events, same order, same count, same fields,
      same values. The key is not reproduced because it was redundant: every
      event already carries `t_ms`, and `*Ended` carries `dur_ms`. Reasoning in
      `tests/contracts/DELTAS.md`.

  **Post-phase a2kit import inventory in `src/`: 8 sites, down from 11.**
  All four `a2kit.log` imports are gone. What remains is `PruneEmpty` in
  `models` (Phase 6) and the spine: `routers.py`, `server.py`, `lazy.py`
  (Phase 4). `src/a2web/packages/` and `src/a2web/events/` are now entirely
  a2kit-free.

## 2. Vendor the TSV codec (independently landable) — **DONE 2026-07-22**

- [x] 2.1 Copied a2kit `0.49.2`'s `formatter/tsv.py` verbatim into
      `src/a2web/_tsv_compat.py`. Body byte-identical; only the module docstring
      differs, and it says loudly that the file is temporary, that its escaping
      is knowingly wrong, and that it must not be "improved" — the whole value
      of a vendored copy is that it does not drift while the goldens are being
      used to prove the substrate swap changed nothing.
- [x] 2.2 Repointed `models.py` (`encode_tsv`). `PruneEmpty` stays on a2kit with
      an inline note that it moves in Phase 6.
- [x] 2.3 Wire goldens **byte-identical** — zero deltas, escape hatch untouched.
- [x] 2.4 **Added beyond plan:** `tests/contracts/test_tsv_vendored_parity.py` —
      18 assertions running BOTH encoders over the same inputs and demanding
      identical output. The goldens only cover cells a2web happens to emit; this
      covers the codec's whole surface, including all five characters that
      trigger `QUOTE_MINIMAL` quoting (i.e. exactly where `lean-wire` will
      legitimately differ) and the `TypeError` message text. It carries an
      explicit "delete me with a2kit, do NOT `importorskip` me" instruction —
      an import-skip would convert a real signal into permanent silence.

## 3. Repatriate `lazy` (independently landable) — **DONE 2026-07-22**

- [x] 3.1 New `src/a2web/lazy.py` owns the 3-line `lazy` thunk outright.
- [x] 3.2 Repointed 12 test files (`from a2web.lazy import lazy`); call sites
      zero-diff, as predicted.
- [x] 3.3 **Scope taken beyond plan, deliberately:** the module also
      **re-exports `Lazy` by identity** and every `src/` module now imports the
      alias from there (`fetcher`, `routers`, `state`, `llm_resource`). It is
      re-exported, never redefined — a2kit's dispatcher matches on that *exact*
      alias object when wiring a tool parameter, so a structurally-identical
      local `TypeAlias` would be a real risk for no gain. This collapses five
      scattered `from a2kit import Lazy` lines into one seam for Phase 4.1 to
      flip.

  **Post-phase a2kit import inventory in `src/` (11 sites, down from 16):**
  `a2kit.log` × 4 (`fetcher`, `state`, `handlers/twitter`, `llm_eval/runner`) →
  Phase 1 clears all four. `PruneEmpty` in `models` → Phase 6. The rest is the
  spine: `routers.py` (decorators), `server.py` (App, config, serve, runtime),
  `lazy.py` (the alias) → Phase 4.

- [x] 3.4 Gate: `make check` green — **1223 passed, 3 xfailed, coverage 90.44%**
      (was 1205 / 90.40%). Wire goldens zero deltas across both phases.

## 4. THE SPINE — atomic, cannot be split — **DONE 2026-07-22**

- [x] 4.1 Write `ResourceScope` (LIFO teardown; record ONLY after a successful
      `__aenter__`) + `Lazy` (memoized async thunk under a construction lock).
      ~27 lines. Port the spike's assertions as unit tests.
- [x] 4.2 One composition root: absorb `bootstrap_state` into
      `build_components(*, <factory overrides>)` returning the router with its
      thunks. Deletes `RobustBrowserBackend` (D5).
- [x] 4.3 D1 — explicit tool signatures: thin FastMCP functions whose parameter
      lists ARE the wire contract, closing over the router bundle. Two tools
      (`query`, `fetch_raw`); `refresh` only if Q1/`expose_cookies_tool` says so.
- [x] 4.4 Register on `fastmcp.FastMCP`; teardown via FastMCP `lifespan=`.
- [x] 4.5 Reproduce the two-piece error mechanism: per-tool wrapper raising
      `ToolError(prose) from exc` + outer middleware recovering the envelope from
      `__cause__`. **A single catch-all middleware does not work** — FastMCP masks
      plain exceptions before middleware sees them.
- [x] 4.6 Health check → `await components.sqlite()`. Retire the
      `Never call _ensure() in a health_check body` rule from `CLAUDE.md`.
- [x] 4.7 Port `serve_http_main` to `mcp.run(transport="http", auth=provider)`.
      The Google OAuth provider path already bypasses a2kit — low risk.
- [x] 4.8 Delete `A2kitConfig`/`McpConfig`, the `code_mode` toggle, and the
      `a2kit[code-mode]` extra.
- [x] 4.9 Remove a2kit from `pyproject.toml`; add `fastmcp>=3.4` directly;
      `uv lock`.
- [x] 4.10 Wire goldens: **zero deltas** on `list_tools` and all call scenarios.
      `_meta.a2kit` disappearing from `list_tools` is the one expected delta —
      accept it under slug `a2kit-meta-removed`.
- [x] 4.11 Un-`xfail` `tests/capabilities/ask_response/test_envelope_dispatch_encoder.py`
      (both scenarios) — the middleware is gone, so they must now pass. Close
      `envelope-wire-hygiene` task 3.1 as superseded-by-deletion.
- [x] 4.12 The non-golden invariant from `wire-contract-golden-gate` §6 must flip
      from xfail to passing: a populated `other_pages` survives into
      `content[0].text`.

  ### What the phase actually cost, versus the estimate

  The proposal's "irreducible substrate: 60–90 lines" covered the DI spine
  only, and was roughly right about it (`scope.py` + `components.py` ≈ 250
  lines including docs, ~90 of code). **What the estimate missed is that
  a2kit also owned the WIRE**, and the wire is the product's contract:

  | Concern | New home | Why it could not be skipped |
  |---|---|---|
  | Envelope encoding + TSV blocks | `wire.py` | it IS `content[0].text` |
  | Typed error envelope + prose | `error_wire.py` | it IS the failure wire |
  | `PruneEmpty` | `wire.py` (pulled fwd from Phase 6) | omit-empty discipline |

  The `EncodingPlan` **inference** was not ported. a2kit derived TSV fields
  from the model's field types at import; `wire._TSV_FIELDS` states them as a
  literal table, transcribed from what inference produced. Same reasoning as
  D1: a2web has two response models, and which fields render as TSV is a
  contract, not something to re-derive. Adding a field to `AskResponse` can no
  longer silently change the wire.

  ### Three wire deltas, all documented in `DELTAS.md` — and two are FIXES

  1. `a2kit-spine-removed` — `_meta.a2kit` gone (a projection of framework
     internals, no consumer), plus one tool-description line that said "a2kit's
     logging channel" and had been false since Phase 1.
  2. `other-pages-tsv-no-longer-destroyed` — **a2kit's encoder was silently
     emptying a populated `other_pages` on the text channel.** `_prune_wire`
     hands it over as an already-encoded TSV *string*; a2kit tested only
     `isinstance(rows, (list, tuple))` and fell through to `[]`. The machine
     channel was right the whole time, so only the agent saw the lie — an
     ADR-0015 violation.
  3. `envelope-presence-guard` — **a2web's own round-17 bug report, fixed by
     owning the code.** `docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md`
     was filed as *"OPEN — no a2web workaround exists"* because a2web had no
     formatter seam. a2kit re-inserted every pruned conditional as `"\n"` plus
     a `_<name>_format` sidecar, so five omitted fields became ten dead keys.
     The minimal success payload went **11 keys → 2**.

  Both fixes were guarded by `xfail(strict=True)` tripwires written when the
  defects were found and deliberately kept OUT of the goldens — a golden
  captured against a broken encoder would have frozen the defect, and a
  faithful port would then have passed the gate. The strict marker is what
  turned "the constraint lifted" into a hard failure that could not be skipped.
  All three tripwires are now un-xfailed and passing.

- [x] 4.13 **Beyond plan — `bootstrap_state` and `Resources` DELETED, not just
      superseded.** Task 4.2 said "absorb"; leaving them would have left the
      exact second composition root 7.2 exists to forbid. The eval CLI and the
      test fixtures now go through `build_components`, and `systems.py` got
      *smaller* — it had been hand-wrapping concrete resources back into
      `Lazy[T]` thunks, which `Components` already provides.

- [x] 4.14 **Beyond plan — `test_framework_matches_the_resolved_mcp_substrate`
      RE-AIMED at `src/a2web` rather than retired.** Its own docstring offered
      both options. Retiring was wrong: a2web now constructs
      `ToolResult(is_error=True)` itself in `error_wire.py`, so the drift risk
      did not leave with a2kit — it moved into this repo. Renamed
      `test_a2web_matches_the_resolved_mcp_substrate`, with a measured floor
      (`checked >= 2`) instead of `> 0`.

- [x] 4.15 **Beyond plan — the Rego policy lint is a recorded LOSS, not a
      silent drop.** `make lint` ended with `uv run a2kit lint rego src/`,
      which fired twice in Phase 1 alone (the `_resolve` and `_safe_emit`
      collisions). Nothing else in `make check` looks for those.
      `policies/data.json` is KEPT (its allowlist rationales are still true and
      are the expensive part to re-derive), the `Makefile` carries the reason
      inline, and re-homing it is `BACKLOG.md` 2026-07-22.

  **Gate: `make check` GREEN — 1212 passed, coverage 90.40%, 36 architecture
  tests.** `grep -rn "import a2kit" src/ tests/` → nothing. `uv.lock` → no
  a2kit. `import a2kit` → `ModuleNotFoundError`.

  **Known regression, deliberate and scoped:** `main()` is a bare stdio MCP
  entrypoint; the Typer CLI (`a2web web query`, `a2web serve`, `a2web health`)
  is gone until Phase 5. **Do NOT run `make install-global` until Phase 5
  lands** — it would replace the binary Claude Code drives with one that has
  no CLI. `make dev` carries the same note.

## 5. The Typer CLI — **Q1 = KEEP** (design: D6)

> **Start with the gate, not the app.** The CLI is a second wire contract and it
> is entirely ungated — 1236 tests, not one of which invokes it. Every byte of
> its current behaviour (compact-JSON separators, the 50k cap, the truncation
> marker, the command tree, the flag names) is inherited and unasserted.
> Hand-writing the Typer app first would make Phase 5 an unverifiable rewrite of
> a surface the user drives daily.

- [x] 5.0 **CLI golden gate, BEFORE any CLI code moves.** Mirror
      `tests/contracts/wire/`: drive the real CLI (`CliRunner` or subprocess)
      with stubbed tiers + frozen clocks, and freeze stdout / stderr / exit code
      per command. Cover `web query`, `web fetch_raw` (incl. `--include-content`
      to reach the truncation path), `health`, `--help` at every level, and at
      least one bad-flag error. Reuse `check_wire`'s two-phase accept protocol.
- [x] 5.1 Vendor a2kit's `packages/cli/_field_to_typer.py` (54 lines) —
      `Annotated[T, pydantic.FieldInfo]` → `Annotated[T, typer.Option(help=…)]`.
      a2web's tool params are already written that way, so the MCP schema's
      descriptions become `--help` text for free.
- [x] 5.2 Generate each Typer command from the D1 FastMCP tool function's
      `inspect.signature` (~40 lines). Safe precisely because D1 removed the
      wire/injected partition guess — the signature is now wire-only by
      construction, so the derivation is total and unambiguous.
- [x] 5.3 Command tree: keep `serve`, `health`, `web query`, `web fetch_raw`,
      `cookies refresh`. **Drop `schema`, `list-tools`, `code`, `_meta`** —
      framework introspection, not product (`code` dies with code-mode in 4.8).
- [x] 5.4 Decide the 50k `truncate` cap + `"... (truncated)"` marker explicitly
      rather than inheriting it — after 5.0 has recorded today's behaviour.
      **DECIDED: dropped.** a2kit exported `truncate()` / `DEFAULT_MAX_CHARS`
      but never called it, so the cap never fired and nothing observed depends
      on it. The recommendation to keep it was wrong on inspection: these
      commands emit ONE JSON document, so slicing the encoded string yields
      unparseable JSON — a caller's `json.loads` crashes on output that looks
      fine in a terminal.
      Recommend keeping it; the point is that the choice becomes visible.
- [x] 5.5 Keep the per-command lifecycle (enter/exit the whole runtime per
      invocation, closing sqlite each time). For a one-shot process that is
      correct, not wasteful. Confirm teardown still runs.
- [x] 5.6 Update the `Makefile` targets and `make install-global`.
- [x] 5.7 CLI goldens: zero deltas against 5.0, or a slugged, reasoned delta.

## 6. Test surface

- [x] 6.1 Rework the six wire-test files (`test_contracts`, `test_ask_response`,
      `test_router_wire`, `test_fetch_response`, `test_listing_options`,
      `test_ask_wire_end_to_end`) — contact is six ~8-line module helpers; the
      ~1350 assertion lines do not move. Fakes are injected via
      `build_components(llm_factory=…)`, not a container override.
- [x] 6.2 Replace `make_client(app)` with `fastmcp.Client(mcp)` (11 sites).
- [x] 6.3 DELETE `tests/architecture/test_no_lambdas_in_app_provide.py`.
- [x] 6.4 DELETE `tests/architecture/test_no_ldd_terminology.py`.
- [x] 6.5 DELETE the four DI-container assertions in `test_app_state.py`; keep the
      genuine `AppState` slots/fields assertions.
- [x] 6.6 **HARDEN** `test_tools_return_pydantic_not_str.py` — retarget the
      decorator matcher AND add `assert len(inspected) >= 2`, or it goes vacuously
      green forever.
- [x] 6.7 **Audit every other AST-walking architecture test for the same vacuity
      trap.** Add a non-vacuity assertion to each. **DONE 2026-07-22, pulled
      forward ahead of Phase 4** — the phase that rewrites the spine is exactly
      when these guards must be able to go red.

      Measured first: **30 of 32 architecture tests passed against an empty
      source tree.** The two survivors (`test_aiosqlite_daemon`,
      `test_record_projection_separates_nodes`) are import-driven, so a missing
      tree raises rather than yields nothing.

      Fix is one shared walker, `tests/architecture/_walk.py::walked_files(root,
      *, minimum)`, asserting the root exists AND the walk clears a floor. All
      **10** rglob sites converted. Floors are deliberately slack — `src/a2web`
      119 files → floor 80, `llm_extract` 10 → 6, `_manifests` 34 → 20 — so
      Phase 4's deletions do not trip them; the floor catches "the walk found
      nothing like what it expected", never the file count.

      `test_walk_is_not_vacuous.py` guards the guard (missing root, empty tree,
      real tree clears its floor) — without it the whole directory could
      silently become optional again.

      Note this covers 6.6's second half for `test_tools_return_pydantic_not_str`
      (the floor is now in place); 6.6's decorator retarget stays Phase 4 work.
- [x] 6.8 Rationale-rewrite (no logic change): `test_aiosqlite_daemon.py`,
      `test_response_models_at_module_scope.py`, `test_no_rogue_structlog.py`.
- [x] 6.9 Port `test_google_oauth.py`'s monkeypatch seam from
      `a2kit.runtime.build`/`serve_process` to the FastMCP equivalent.

## 7. Lock the discipline that the framework used to enforce

- [x] 7.1 **Cold-start architecture test** (the mitigation for the honest risk):
      a `query` served from cache or the raw tier must leave the browser and LLM
      thunks **unresolved**. This is the spike's R1 assertion promoted into
      `tests/architecture/`.
- [x] 7.2 **One-composition-root architecture test**, mirroring a2kay.
- [x] 7.3 Update the `Never` rules in `CLAUDE.md`: drop the a2kit-specific ones
      (`app.singleton`, `a2kit.Param`, `idempotent=`, `lifespan=`,
      `canonical_name_override`, `_ensure()` in health checks), add the two new
      structural rules above.

## 8. Ship

- [ ] 8.1 `make check` green; coverage ≥85%.
- [ ] 8.2 `make bench` — the envelope and extraction paths moved; confirm the
      clarity and conformance axes held.
- [ ] 8.3 `make install-global`; verify the live MCP server in a fresh Claude Code
      session still advertises `query` + `fetch_raw` and serves a real fetch.
- [ ] 8.4 Notify a2kit that its last consumer has migrated — a2kit can drop
      maintenance mode and proceed with dissolution.

## 9. Follow-on (separate change, NOT here)

- [ ] 9.1 Adopt `lean-wire` (`PruneEmpty` + `encode_tsv`), delete
      `_tsv_compat.py`, re-bless goldens under slug `lean-wire-escaping`, record
      the wire-format bump in `CHANGELOG.md`. Requires shelf `work/a2kay` merged
      to `main` (task 0.3).
