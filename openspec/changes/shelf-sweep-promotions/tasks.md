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
  5. `any-browser` SEAM ← `packages/browser_backends/` (types only; hold drivers, task 5.2b)
- **Blocker for autonomous execution:** the repoint step (delete in-tree copy)
  and the dead-leftover cleanup both require `git rm` in the a2web repo, which
  the auto-mode classifier denies. The shelf worktree exists at
  `../shelf-a2web` (branch `work/a2web`, reset to `main` 2026-07-26).

## 0. Gate and setup

- [ ] 0.1 Human sign-off on the `design.md` verdict table. **All four open
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
- [ ] 0.3 Create the worktree: `git -C <shelf> worktree add ../shelf-a2web -b work/a2web`.

### 0.4 Promotion-boundary invariants (binding on EVERY promotion below)

Derived from the verification-provenance review (2026-07-26); full rationale in
`docs/architecture/verification-provenance.md`. Expected-loss order — the thing
most likely to hurt a consumer we don't control is a package that installs clean
here and nowhere else, NOT an endogenous golden. No package is tagged until:

- [ ] 0.4a **Foreign-soil install-and-run (THE gate).** Install the package from
      its tag into a clean env with no repo checkout and none of a2web's
      incidental deps; run its acceptance suite against the *installed artifact*.
      Catches undeclared deps, missing `py.typed`, packaging holes, and
      graceful-absence paths (which never run on home soil). Shelf-side CI; port
      the a2web `browser-gate` skip-forbidden pattern.
- [ ] 0.4b **Pin, never `path=`.** Promotion is done only when a2web's full gate
      is green pinned to the *published tag*, not the worktree.
- [ ] 0.4c **Boundary enums get an exhaustive `match` + `assert_never` in the
      consumer** (type drift already happened: `ProviderMode` vs
      `anyllm.ProviderName`). Drift then breaks at type-check — a compile-time
      witness.
- [ ] 0.4d **Tags are immutable.** A bad tag → ledger row + superseding tag,
      never a deletion/force-push (mirrors the shelf's "never delete an old
      tag").
- [ ] 0.4e **Exogenous-witness flake budget.** Real-substrate lanes (browser,
      bench, foreign-soil) get a separate signal + triage SLA; an ignorable red
      is mechanism A wearing mechanism B's coat.
- [ ] 0.4f **Standing fake-fidelity contract** for any external-dep fake in a
      promoted package (pattern:
      `test_zendriver_backend.py::test_fake_config_matches_real_add_argument`).
      The H2 sweep found the candidates clean *today*; this keeps them clean
      across dependency bumps.
      Then `git fetch && git rebase origin/main` **before touching any file**
      (worktrees share objects but not branch position).
- [ ] 0.4 All shelf edits happen in `../shelf-a2web`. Never edit the shelf main
      checkout.

## 1. PROMOTE `plugin-surface`

- [ ] 1.1 Extract `_plugin.py` into `packages/plugin-surface/` behind the
      Capability in `design.md`. Drop `settings_prefix` (an invented no-op field).
- [ ] 1.2 Boundary test: must not import any consumer app.
- [ ] 1.3 Port `tests/plugin_framework/` as the package's acceptance suite.
- [ ] 1.4 Contract born `candidate`. `make check` green **in the worktree**.
- [ ] 1.5 Tag `plugin-surface-v0.1.0`; push branch + tags.

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

## 3. EVOLVE `anyllm` (cost + prompt)

- [ ] 3.1 Add `anyllm.cost` (`CostPolicy`, `assert_within_budget`,
      `with_cost_guard`, `CostViolation`). Key the policy on `ProviderName`, not
      on a2web's manifest strings.
- [ ] 3.2 Add `anyllm.prompt` (`PromptTemplate`) beside the `PromptParts` it
      already owns.
- [ ] 3.3 Monotonicity check (resolution 0007): exposes more, removes nothing.
- [ ] 3.4 Port `tests/packages/test_llm_cost_guard.py`.
- [ ] 3.5 Tag `anyllm-v0.5.0`. No `CHANGELOG.md` entry needed unless a contract
      shape changed (additive → usually zero lines).

## 4. PROMOTE `llm-cache`

- [ ] 4.1 Extract `packages/llm_extract/cache.py` on `sqlite-resource` + `anyllm`.
- [ ] 4.2 Shape change at extraction: return `anyllm.Completion` rather than a
      bespoke `ExtractionCacheRow` (the fields already match).
- [ ] 4.3 Boundary test; acceptance suite. Tag `llm-cache-v0.1.0`.

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
- [ ] 5.2a **Promote the SEAM now** — `BrowserBackend` Protocol, `RenderedPage`,
      `BackendCookie`, `RenderOutcome`. Pure types, no launch behaviour, nothing
      environment-conditional to fake — mechanism-A endogeneity has no purchase.
      This is the genuine catalog gap and the real ADOPT case (the Protocol
      demonstrably spans engine families: Playwright API + raw CDP).
- [ ] 5.2b **HOLD the drivers** (`PlaywrightBackend`, `ZendriverBackend`,
      launchers) until a shelf-side **real-launch gate** exists: a CI lane that
      launches BOTH engines against a real page and asserts a render, with
      skip-on-missing-binary **forbidden** in that lane (a skip in the one
      environment you control is a dead rung wearing a green coat — that is
      literally how the 2026-07-25 dead rung stayed green). Only then extract the
      drivers. The extracted acceptance suite is NOT this gate — it shares
      provenance with the code and detects drift, not correctness.
      **Reference implementation now exists a2web-side (2026-07-26, commit
      `14aeef1`):** the `browser-gate` CI job + `A2WEB_REQUIRE_BROWSER=1`
      skip→fail policy (`test_browser_smoke.py::browser_unavailable_policy`,
      pinned in the default gate by `test_browser_gate_policy.py`). The shelf
      gate is this pattern, moved to the shelf's CI over the promoted drivers —
      port it, don't reinvent it. Until then a2web itself is the only place the
      drivers get a real-launch witness, which is another reason the shelf copy
      must not ship without one.
- [ ] 5.2c **Absorbs `fix-zendriver-robust-rung` §1–§2** (folded 2026-07-26 — that
      change archived). Its blocked diagnosis (zendriver dead on CDP handshake in
      the image) IS what the 5.2b real-launch gate produces: run the gate, and if
      zendriver fails to launch, that is the diagnosis. Then the fix-or-drop branch
      resolves — **fix** the launch in `zendriver.py`, or **drop** it and promote a
      genuinely distinct second engine for `browser_robust` (differentiated stealth
      profile or reinstated Camoufox), never a same-engine (correlated) witness.
      Retire the homelab correlated-witness workaround the moment a distinct engine
      passes the gate; the `CorrelatedWitnessRung` signal (fix-zendriver §3, DONE)
      is the detectable revert-trigger. `make bench` once the robust engine
      actually changes (fix-zendriver §4.2, was deferred).
- [ ] 5.3 Per Q2 (answered 2026-07-25): **keep** `subresource_blocks` on the
      promoted `RenderedPage`, but rewrite the docstring to describe the
      observation (subresources returning a challenge status during render),
      NOT a2web's "walled-API fake-empty signal" conclusion — that meaning stays
      home in `actions/terminal.py` + `actions/empty.py`. (Separately: the
      zendriver-never-populates-it bug is filed in `BACKLOG.md`, an a2web fix,
      not a promotion blocker.)
- [ ] 5.4 Confirm the moat stays home: `select_backend*`, the manifest gating, the
      fast/robust rung split, the `RenderOutcome → Verdict/OperatorHint` mapping.
- [ ] 5.5 Port `tests/packages/test_playwright_backend.py` +
      `test_zendriver_backend.py`. Tag `any-browser-v0.1.0`.

## 6. `structured-data-md` (only if Q3 resolves to promote)

- [x] 6.1 **DONE 2026-07-22 — contamination CONFIRMED.** Re-read `_rows_to_md_table` / `_render_rows` for a2web wire-style
      leakage before extracting.
- [x] 6.2 **DECIDED: neither, as posed.** The candidate splits — rendering is
      product (KEEP), normalization is the real gap (EVOLVE `json-in-html`,
      deferred pending boundary design). See proposal Q3.
- [x] 6.3 ~~If promoting: extract, port `tests/capabilities/json_extract/`, tag.~~
      **Not promoting in this sweep** — see 6.2.

## 7. Repoint a2web (Phase E step 6 — per package, tests green each time)

- [ ] 7.1 Add each git+tag source to `pyproject.toml`; `uv lock`.
- [ ] 7.2 Delete each in-repo copy; update imports.
- [ ] 7.3 Adopt `anyllm.ProviderName` at the settings field: `ProviderMode
      = Literal[...]` → `provider: ProviderName` on the `BaseSettings` field
      (`settings.py:30`). `StrEnum` is natively a pydantic validator — no custom
      `field_validator`. Everything downstream becomes `ProviderName`-typed.
- [ ] 7.4 Add an exhaustive `match`/`case` with `assert_never` on the fallback
      (no wildcard) so a future anyllm provider addition fails statically.
- [ ] 7.5 Confirm `tests/test_packages_independence.py` still passes and the
      `packages/*/__init__.py` `__all__` freeze test reflects the removals.
- [ ] 7.6 `make check` green in a2web after each repoint.

## 8. Close the loop (resolution 0009 — the change isn't done until `main` carries it)

- [ ] 8.1 `use-cases/a2web--<sw>.toml` per adopted piece (the retention claim).
- [ ] 8.2 A `ledger/00NN-<slug>.toml` **`delivery`** row per promotion, and a
      **separate** `verdict` row per repoint that held. Two events, two rows —
      never one row wearing both hats. Grep `ledger/*.toml` for `^event` for the
      existing vocabulary; do not invent one.
- [ ] 8.3 `make catalog` (a stale derived README lies).
- [ ] 8.4 Delete the closed `docs/backlog.md` line for "a2web adopts
      `anyllm.ProviderName`"; edit any partially-closed line to say what remains.
- [ ] 8.5 `make check` green, then **merge `work/a2web` into `main` and push** —
      a promotion that never reaches `main` never happened.
- [ ] 8.6 `git worktree remove ../shelf-a2web`; delete the merged remote branch.

## 9. Report (Phase F)

- [ ] 9.1 Publish the candidate → verdict → action table plus **what the shelf
      gained** (packages promoted / capabilities extended). The success metric is
      future-code-avoided, not a2web shrink.

## 10. Follow-up filed, not done here

- [ ] 10.1 Open a RECONCILE-pass question from Q4: is a2web running **two
      independent health-degradation mechanisms** (`_ProxyHealth` quarantine and
      the `purgatory` circuit breakers, `state.py:86-88`)? Not a promote question
      — a design-smell investigation.
