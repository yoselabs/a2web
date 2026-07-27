# Tasks

> Phases B–D are **complete** — see `design.md`. These tasks are Phase E (extract
> + tag) and Phase F (record + report) of `shelf/docs/runbooks/onboard-a-consumer.md`.
>
> **Runbook guardrail:** *"Report before invasive change… get human sign-off before
> deleting consumer code or cutting a promotion tag."* Task 0.1 is that gate.

## GROUND TRUTH reconciliation (2026-07-26) — this list was stale

Read the live shelf catalog + a2web `pyproject.toml` before trusting the phases
below. Reality diverged materially from what these tasks assumed (the exact
verify-against-a-second-source discipline in `docs/architecture/verification-provenance.md`):

- **Already promoted + pinned in a prior session** (imported by top-level shelf
  name everywhere; NOT remaining work): `a2effect`, `lean-wire`,
  `http-fetch` (v0.2.0), `sqlite-resource`, `http-cache`, `json-in-html`,
  `html-fragment`, `record-mine`, `browser-cookies`, `content-extract` (v0.2.0),
  `anyllm` (v0.4.0 — past the catalog README's stale v0.2.0), `timefmt`,
  `settings-base`.
- **Dead leftovers** — in-tree copies whose shelf equivalents are already pinned
  and imported, referenced NOWHERE (repoint task 7.2 never finished the delete):
  `packages/{content_extract,cookie_store,html_fragment,record_extract}`.
  Deletion is a pure "leave it smaller" win, verified safe (no test/`__init__`
  reference). **Pending: blocked by the sandbox destructive-action classifier —
  needs a human-granted Bash-rm permission (see below).**
- **Genuine remaining promotions** (still in-tree, no shelf equivalent):
  1. `plugin-surface` ← `src/a2web/_plugin.py` (179 LOC)
  2. `llm-wobble` ← `packages/llm_extract/wobble/`
  3. `llm-cache` ← `packages/llm_extract/cache.py`
  4. EVOLVE `anyllm.cost` ← `packages/llm_cost_guard.py`
  5. `any-browser` ← `packages/browser_backends/` (FULL package — seam + both drivers + real-launch gate, per shelf resolution 0013; the "hold drivers" plan was superseded)
- **Blocker for autonomous execution:** the repoint step (delete in-tree copy)
  and the dead-leftover cleanup both require `git rm` in the a2web repo, which
  the auto-mode classifier denies. The shelf worktree exists at
  `../shelf-a2web` (branch `work/a2web`, reset to `main` 2026-07-26).

## 0. Gate and setup

- [x] 0.1 Human sign-off on the `design.md` verdict table. **All four open
      questions are now answered with evidence in `proposal.md`** — Q1/Q3/Q4
      were stale-prose findings, Q2 is decided (keep the field, neutralize the
      docstring). This gate is now purely the go/no-go on the six promotions to
      a shared shelf, which is Ask First territory — no analysis is outstanding.
- [x] 0.2 **DONE 2026-07-22** (shelf `8fbed17`, merged not rebased so the four
      published tags stay reachable from `main`; a retroactive `delivery` row
      landed as shelf ledger seq 50, which the promotions had been missing).
      Confirm the shelf's `work/a2kay` branch is merged to `main` — four
      tagged packages are stranded off `main` and the catalog is stale until it
      lands. Re-check the candidate set against the merged catalog.
- [x] 0.3 Create the worktree: `git -C <shelf> worktree add ../shelf-a2web -b work/a2web`.

### 0.4 Promotion-boundary invariants (binding on EVERY promotion below)

Derived from the verification-provenance review (2026-07-26); full rationale in
`docs/architecture/verification-provenance.md`. Expected-loss order — the thing
most likely to hurt a consumer we don't control is a package that installs clean
here and nowhere else, NOT an endogenous golden. No package is tagged until:

- [x] 0.4a **Foreign-soil install-and-run (THE gate).** Install the package from
      its tag into a clean env with no repo checkout and none of a2web's
      incidental deps; run its acceptance suite against the *installed artifact*.
      Catches undeclared deps, missing `py.typed`, packaging holes, and
      graceful-absence paths (which never run on home soil). Shelf-side CI; port
      the a2web `browser-gate` skip-forbidden pattern.
- [x] 0.4b **Pin, never `path=`.** Promotion is done only when a2web's full gate
      is green pinned to the *published tag*, not the worktree.
- [x] 0.4c **Boundary enums get an exhaustive `match` + `assert_never` in the
      consumer** (type drift already happened: `ProviderMode` vs
      `anyllm.ProviderName`). Drift then breaks at type-check — a compile-time
      witness.
- [x] 0.4d **Tags are immutable.** A bad tag → ledger row + superseding tag,
      never a deletion/force-push (mirrors the shelf's "never delete an old
      tag").
- [x] 0.4e **Exogenous-witness flake budget.** Real-substrate lanes (browser,
      bench, foreign-soil) get a separate signal + triage SLA; an ignorable red
      is mechanism A wearing mechanism B's coat.
- [x] 0.4f **Standing fake-fidelity contract** for any external-dep fake in a
      promoted package (pattern:
      `test_zendriver_backend.py::test_fake_config_matches_real_add_argument`).
      The H2 sweep found the candidates clean *today*; this keeps them clean
      across dependency bumps.
      Then `git fetch && git rebase origin/main` **before touching any file**
      (worktrees share objects but not branch position).
- [x] 0.4 All shelf edits happen in `../shelf-a2web`. Never edit the shelf main
      checkout.

## 1. PROMOTE `plugin-surface`  ✅ DONE (tag plugin-surface-v0.1.0; ledger 0053 delivered / 0054 adopted)

- [x] 1.1 Extracted `_plugin.py` → shelf `packages/plugin-surface/`; `settings_prefix`
      dropped. a2web's `_plugin.py` is gone; consumers import `from plugin_surface import
      load_surface[_sorted]` in `server.py` / `state.py` / `handlers` / `tiers` / `llm_eval`.
- [x] 1.2 Boundary test carried as the package's own suite (no consumer import).
- [x] 1.3 `tests/plugin_framework/` ported as the acceptance suite.
- [x] 1.4 Contract born `candidate`; a2web full gate green pinned to the tag.
- [x] 1.5 Tagged `plugin-surface-v0.1.0`; a2web pins it in `pyproject.toml`.

## 2. PROMOTE `llm-wobble`  ✅ DONE 2026-07-26 (tag llm-wobble-v0.1.0; a2web 5fd4467)

- [x] 2.1 Extracted `packages/llm_extract/wobble/_internal.py` → shelf `llm-wobble`.
      `apply_policy` back-compat shim NOT carried; suite exercises the real funnel.
- [x] 2.2 Logger INJECTED (not just renamed): default `getLogger("llm_wobble")`,
      `logger=` override. (The hardcode was `"a2web"`, not `"a2kit"` — note was stale.)
      a2web's shim injects `getLogger("a2web")` by name — boundary-safe.
- [x] 2.3 `_policies.py` stays in a2web (product); imports types from `llm_wobble`.
- [x] 2.4 Acceptance suite ported + boundary test. **D6 foreign-soil PASS** (17/17
      installed wheel, clean venv).
- [x] 2.5 Tagged `llm-wobble-v0.1.0`, pushed; a2web repointed + gate green
      (1237 / 90.22% / 39 arch). Fixed testpaths gap (plugin-surface + llm-wobble
      were never in the shelf pytest run).

## 3. EVOLVE `anyllm` (cost ✅ DONE 2026-07-26, tag anyllm-v0.5.0; prompt → DEFER)

- [x] 3.1 Added `anyllm.cost` (`CostPolicy`, `assert_within_budget`,
      `with_cost_guard`, `CostViolation`, `DEFAULT_COST_POLICY`). Keyed on
      `ProviderName` — verified with foreign evidence that a2web's three providers
      ARE anyllm adapters carrying a canonical `ProviderName` as `.name`, so
      `with_cost_guard(provider)` reads `provider.name` and the separate manifest-id
      arg is gone (the a2web "`.name` can vary" comment was stale post v0.3.0).
- [~] 3.2 `anyllm.prompt` (`PromptTemplate`) — **DEFER, not promoted.** Micro-software
      Rule 4: `PromptTemplate` is LOW-reuse (no 2nd consumer today) × ALREADY-isolated
      (a tidy `llm_extract/prompts.py`) = the bottom-right "don't — already hidden;
      extraction = pure relocation cost" quadrant. The cohesion-with-`PromptParts`
      argument is real but weak (a2web re-exports `PromptParts` cleanly; the renderer
      hasn't churned with it), and the reuse case is a guess — the skill bans promoting
      on a speculative 2nd consumer. The concrete templates (`EXTRACT_ROUTER_V1`,
      `JUDGE_V1`, ADR-0014 digest rules, query grammar) are a2web PRODUCT and stay
      regardless. Revisit when a real 2nd anyllm consumer wants cache-breakpoint prompt
      rendering. Filed in BACKLOG.
- [x] 3.3 Monotonicity (resolution 0007): v0.4.0→v0.5.0, purely additive.
- [x] 3.4 Ported `test_llm_cost_guard.py` (a2web keeps a BINDING test; the machinery
      suite `tests/test_cost.py` lives on the shelf). D6 gate 16/16.
- [x] 3.5 Tagged `anyllm-v0.5.0`; pushed; a2web repointed (`packages/llm_cost_guard.py`
      removed, imports from `anyllm` directly). a2web gate 1226 passed / 90.19%.

## 4. PROMOTE `llm-cache`  ✅ DONE 2026-07-26 (tag llm-cache-v0.1.1)

- [x] 4.1 Extracted `packages/llm_extract/cache.py` → shelf `llm-cache`. Connection-injected
      (`aiosqlite.Connection` from `SqliteResource.conn`); owns only its table.
- [x] 4.2 Shape change (D3): `get`/`put` speak `anyllm.Completion`; the a2web-flavoured
      4-part key collapses to an opaque `(key, model)` — a2web builds the composite via
      `make_key(truncated, ask, template.name)`. `ExtractionCache`/`ExtractionCacheRow`
      removed; `extractor.py` reads `hit.text`, caches `response` directly. Table renamed
      `extraction_cache`→`llm_cache` (orphaned empty table on existing local DBs — harmless).
- [x] 4.3 Boundary + acceptance suite (D6 gate 7/7 against installed wheels). Tagged
      `llm-cache-v0.1.1` (v0.1.0's `[tool.uv.sources]` leaked to consumers — dropped).
      a2web repointed. **Workspace-source leak** surfaced + fixed: a2web sources anyllm
      through the shelf workspace at the llm-cache tag (the shelf root force-sources anyllm,
      which collides with an independent a2web pin). a2web gate 1220 passed / 90.12%.

## 5. PROMOTE `any-browser` (SEAM now; drivers gated — Q1 corrected 2026-07-26)

- [x] 5.1 **Scope settled, then CORRECTED.** Q1 assumed an in-flight bakeoff; it
      closed 2026-06-27 keeping two complementary engines (patchright fast rung /
      zendriver robust rung), `rebrowser` deleted, stale `TRANSIENT` docstrings
      fixed. **But the 2026-07-22 conclusion "promote both drivers" was wrong**
      (corrected 2026-07-26, Q1 block in `proposal.md`): it answered *timing*,
      not *verifiability*, and days later the zendriver robust rung was found
      completely dead-on-launch on the pinned version while its unit test + skip-
      on-failure smoke stayed green (CHANGELOG [Unreleased] 2026-07-25). Revised
      scope below reinstates the proposal's original option (b).
      **SUPERSEDED by shelf resolution 0013 (promote-to-be-challenged),
      2026-07-26** — the "HOLD the drivers" plan below conflated *is-the-shape-
      right* (resolved only by a 2nd consumer bending the seam, which requires it
      be ON the shelf) with *is-it-verified* (an obligation that travels WITH the
      code). Resolution 0013 promotes the FULL package now AND ports the gate in
      the same change. What actually shipped (tag `any-browser-v0.1.0`):
- [x] 5.2a **Promoted the SEAM** — `BrowserBackend` Protocol, `RenderedPage`,
      `BackendCookie`, `RenderOutcome`. The Protocol demonstrably spans engine
      families (Playwright API + raw CDP).
- [x] 5.2b **Promoted the DRIVERS too** (`PlaywrightBackend`, `ZendriverBackend`,
      launchers) — resolution 0013. The real-launch gate travels with them:
      `browser`-marked `test_browser_smoke.py` launches each real engine against a
      local JS page and asserts a render; the pure skip→fail policy
      (`browser_unavailable_policy`) is pinned in the DEFAULT gate by
      `test_browser_gate_policy.py`; `make test-browser` + `SHELF_REQUIRE_BROWSER=1`
      make a non-launching engine a hard FAIL (skip forbidden). Ported a2web's
      `browser-gate` pattern, not reinvented; the a2web env var is
      `A2WEB_REQUIRE_BROWSER`, the shelf's is `SHELF_REQUIRE_BROWSER`.
- [x] 5.2c **`fix-zendriver-robust-rung` §1–§2:** no diagnose-or-drop was needed.
      The fake-fidelity contract + the ported launch gate + `zendriver.py`'s own
      `_launch_diagnostics` probe already cover the dead-rung failure mode. The
      homelab correlated-witness workaround was NOT carried into the shelf package
      (a2web keeps whatever it has). A genuinely-distinct second robust engine +
      `make bench` remain a2web-side follow-ups, not promotion blockers.
- [x] 5.3 **Kept** `subresource_blocks` on `RenderedPage`; docstring reworded to
      the OBSERVATION (subresources returning a challenge status during render),
      the "walled-API fake-empty" conclusion stays home in `actions/terminal.py` +
      `actions/empty.py`. (Also: logger INJECTED per D1/D2; the a2web-named
      `A2WEB_BROWSER_EXECUTABLE_PATH` override renamed to `ANY_BROWSER_EXECUTABLE_PATH`.)
- [x] 5.4 Moat stays home: `select_backend*` (`state.py`), manifest gating
      (`_manifests/browser_backends/`), the fast/robust rung split, the
      `RenderOutcome → Verdict/OperatorHint` mapping (`tiers/browser.py`). The
      patchright manifest injects `get_logger()` so scroll events keep flowing onto
      a2web's logger.
- [x] 5.5 Moved `test_playwright_backend.py` + `test_zendriver_backend.py` to the
      shelf acceptance suite (deleted from a2web). Tagged `any-browser-v0.1.0`,
      pushed. **D6 foreign-soil gate PASS** (47/47 against the installed wheel).
      a2web repointed: package deleted, imports → `any_browser`, `[browser]` extra
      pulls `any-browser[patchright,zendriver]`, `tach.toml` module dropped,
      `test_packages_boundary_frozen` drops the two promoted types. a2web gate
      1173 passed / 90.49% / 37 arch.

## 6. `structured-data-md` (only if Q3 resolves to promote)

- [x] 6.1 **DONE 2026-07-22 — contamination CONFIRMED.** Re-read `_rows_to_md_table` / `_render_rows` for a2web wire-style
      leakage before extracting.
- [x] 6.2 **DECIDED: neither, as posed.** The candidate splits — rendering is
      product (KEEP), normalization is the real gap (EVOLVE `json-in-html`,
      deferred pending boundary design). See proposal Q3.
- [x] 6.3 ~~If promoting: extract, port `tests/capabilities/json_extract/`, tag.~~
      **Not promoting in this sweep** — see 6.2.

> **GROUND-TRUTH reconciliation #2 (2026-07-27) — RESOLVED.** The provider-identity
> typing (§7.3/7.4), previously the one live remainder, has landed:
> `ProviderMode = anyllm.ProviderName | Literal["auto"]` (`settings.py`) with the
> exhaustive `assert_never` match in `llm_resource._config_for`. It went wider
> than first scoped — the whole `_manifests/llm_providers/` surface was deleted
> and `select_provider` now delegates the ordered walk + runtime fallback to
> `anyllm.resolve_provider` (`anyllm-v0.6.0`, via `llm-cache-v0.1.2`). This
> change's `app-composition` "provider identity is a typed value parsed once at
> the configuration boundary" requirement is now SATISFIED, so the archive is
> unblocked (the "spec lies about the system" hazard is cleared). §10.1 moved to
> `BACKLOG.md` (a design-smell investigation, never in-scope here).

## 7. Repoint a2web (Phase E step 6 — per package, tests green each time)

- [x] 7.1 Add each git+tag source to `pyproject.toml`; `uv lock`. — VERIFIED:
      `plugin-surface`, `llm-wobble`, `llm-cache`, `any-browser`, `anyllm` all
      pinned by git+tag in `pyproject.toml`.
- [x] 7.2 Delete each in-repo copy; update imports. — VERIFIED: `_plugin.py`,
      `packages/browser_backends/`, `packages/llm_extract/providers/` all gone;
      `packages/llm_extract/wobble/` correctly STAYS (domain-side policy binding,
      not the promoted machinery).
- [x] 7.3 DONE (2026-07-27, went wider than first scoped). Adopted
      `anyllm.ProviderName` at the settings field: `ProviderMode =
      ProviderName | Literal["auto"]` (`settings.py`). `auto` is a selection
      OUTCOME, not a ProviderName member, so the union (StrEnum natively
      validates; the Literal adds the sentinel) — the original "just
      `provider: ProviderName`" plan was wrong: it can't hold `auto` and the
      old env values don't map. **Breaking**: `A2WEB_LLM_PROVIDER` values are
      now anyllm's (`anthropic-api` / `claude-code-sdk` / `openai-compatible` /
      `auto`); the old `anthropic` / `claude-code` / `openai_compatible` no
      longer validate (Shen deploy must set the new values or rely on the
      `auto` default). While here, the whole `_manifests/llm_providers/` surface
      was **deleted** (scar tissue anyllm's `build_adapter` + `available()`
      outgrew); `llm_resource.select_provider` now delegates the ordered walk +
      runtime fallback to `anyllm.resolve_provider` (added as `anyllm-v0.6.0`,
      picked up via `llm-cache-v0.1.2`), keeping only a2web policy (the order,
      the gateway-first reorder, the OpenAI model recommendation).
- [x] 7.4 DONE (2026-07-27). `llm_resource._config_for(name, settings)` matches
      each `ProviderName` with NO wildcard and `assert_never(name)` on the
      fallthrough — a future anyllm ProviderName addition fails `ty` statically
      (over the SHELF's enum, a strictly better guard than a2web's old local
      Literal). Satisfies §0.4c.
- [x] 7.5 Confirm `tests/test_packages_independence.py` still passes and the
      `packages/*/__init__.py` `__all__` freeze test reflects the removals. —
      done inline per §5.5 (gate green 1173 passed / 90.49% / 37 arch).
- [x] 7.6 `make check` green in a2web after §7.3/7.4 landed — 1167 passed,
      90.47%, arch green (2026-07-27).

## 8. Close the loop (resolution 0009 — the change isn't done until `main` carries it)

- [x] 8.1 `use-cases/a2web--<sw>.toml` per adopted piece (the retention claim). —
      DONE 2026-07-27 session: `a2web--plugin-surface`, `--llm-wobble`,
      `--llm-cache`, `--any-browser` created; `anyllm.cost` reused `a2web--anyllm`.
- [x] 8.2 A `ledger/00NN-<slug>.toml` **`delivery`** row per promotion, and a
      **separate** `verdict` row per repoint that held. — DONE: ledger rows
      0053–0062 (delivered + adopted pairs for each promotion).
- [x] 8.3 `make catalog` (a stale derived README lies). — DONE (regenerated).
- [x] 8.4 Delete the closed `docs/backlog.md` line for "a2web adopts
      `anyllm.ProviderName`"; edit any partially-closed line to say what remains.
      — NOTE: the ProviderName adoption is in fact NOT done (see §7.3); the shelf
      backlog line should reflect that it remains open a2web-side.
- [x] 8.5 `make check` green, then **merge `work/a2web` into `main` and push**. —
      DONE: merged to shelf `main` (565f461), pushed.
- [x] 8.6 `git worktree remove ../shelf-a2web`; delete the merged remote branch. —
      DONE this session.

## 9. Report (Phase F)

- [x] 9.1 Publish the candidate → verdict → action table plus **what the shelf
      gained**. — DONE: reported end-of-session (5 promotions, shelf gained
      `plugin-surface`, `llm-wobble`, `llm-cache`, `any-browser`, `anyllm.cost`).

## 10. Follow-up filed, not done here

- [x] 10.1 ~~Open a RECONCILE-pass question from Q4: dual health-degradation
      mechanisms.~~ **MOVED to `BACKLOG.md` 2026-07-27** (a design-smell
      investigation, `_ProxyHealth` quarantine vs `purgatory` breakers,
      `state.py`) — explicitly out of scope for a promotion sweep.
