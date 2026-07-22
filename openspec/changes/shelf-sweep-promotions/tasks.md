# Tasks

> Phases B–D are **complete** — see `design.md`. These tasks are Phase E (extract
> + tag) and Phase F (record + report) of `shelf/docs/runbooks/onboard-a-consumer.md`.
>
> **Runbook guardrail:** *"Report before invasive change… get human sign-off before
> deleting consumer code or cutting a promotion tag."* Task 0.1 is that gate.

## 0. Gate and setup

- [ ] 0.1 Human sign-off on the `design.md` verdict table, and on open questions
      Q1 (`any-browser` bakeoff timing), Q2 (`subresource_blocks`),
      Q3 (`structured-data-md` confidence), Q4 (`proxy_routing` / double
      health-degradation).
- [x] 0.2 **DONE 2026-07-22** (shelf `8fbed17`, merged not rebased so the four
      published tags stay reachable from `main`; a retroactive `delivery` row
      landed as shelf ledger seq 50, which the promotions had been missing).
      Confirm the shelf's `work/a2kay` branch is merged to `main` — four
      tagged packages are stranded off `main` and the catalog is stale until it
      lands. Re-check the candidate set against the merged catalog.
- [ ] 0.3 Create the worktree: `git -C <shelf> worktree add ../shelf-a2web -b work/a2web`.
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

## 2. PROMOTE `llm-wobble`

- [ ] 2.1 Extract `packages/llm_extract/wobble/`. **Do not carry `apply_policy`**
      (`_internal.py:186`, self-declared back-compat shim).
- [ ] 2.2 Parameterize the logger name (currently hardcoded
      `logging.getLogger("a2kit")`).
- [ ] 2.3 Leave `_policies.py`'s tables in a2web — they are product.
- [ ] 2.4 Port `tests/packages/llm_extract/test_wobble.py`. Boundary test.
- [ ] 2.5 Tag `llm-wobble-v0.1.0`.

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

## 5. PROMOTE `any-browser` (scope set by Q1)

- [ ] 5.1 Per Q1: promote seam + drivers now, OR seam only pending the
      browser-backend bakeoff verdict.
- [ ] 5.2 Extract `BrowserBackend` Protocol, `RenderedPage`, `BackendCookie`,
      `RenderOutcome`, and (if Q1 says so) `PlaywrightBackend` / `ZendriverBackend`
      + the launcher functions.
- [ ] 5.3 Per Q2: decide `subresource_blocks` — keep in the promoted type with a
      neutral docstring, or leave a2web-side.
- [ ] 5.4 Confirm the moat stays home: `select_backend*`, the manifest gating, the
      fast/robust rung split, the `RenderOutcome → Verdict/OperatorHint` mapping.
- [ ] 5.5 Port `tests/packages/test_playwright_backend.py` +
      `test_zendriver_backend.py`. Tag `any-browser-v0.1.0`.

## 6. `structured-data-md` (only if Q3 resolves to promote)

- [ ] 6.1 Re-read `_rows_to_md_table` / `_render_rows` for a2web wire-style
      leakage before extracting.
- [ ] 6.2 Decide composite-sibling vs `json-in-html` evolution.
- [ ] 6.3 If promoting: extract, port `tests/capabilities/json_extract/`, tag.

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
