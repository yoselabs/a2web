# Architecture invariants

a2web encodes its architecture in code, not in prose. Every rule that
matters has a test that fails CI on violation. ADR-0001
(`docs/adr/0001-structural-prevention-over-vigilance.md`) captures the
reasoning; this README is the operator manual.

## The fitness-function stack

Two tools, each handling what the other can't:

| Tool | Sees | Used for |
|---|---|---|
| **Tach** (`tach.toml`) | Module-to-module imports | Boundary contracts. "`packages/X` is private; only `__init__` is public". "`packages/X` may not depend on `a2web.<domain>`". |
| **pytest-archon + AST** (`tests/architecture/`) | Call sites, decorators, class bodies, type annotations | Anything Tach can't see. JSON-loads ban, no-lambdas-in-`app.provide`, no `dict[str, Any]` on dataclasses, etc. |

`make arch` runs both. `make check` runs `make arch` as part of the gate.

## Adding a new rule

1. **Decide which tool.** Module-boundary → Tach. Call-site / signature /
   class-shape → archon (plain pytest + `ast`).
2. **Write the rule.**
   - Tach: edit `tach.toml`, add the desired `depends_on` constraint, run
     `uv run tach check`.
   - archon: add a `test_*.py` under `tests/architecture/`. Style: AST walker
     + violations list + `assert not violations, "..."`. See
     `test_json_loads_funnel.py` for the canonical shape, with a "how to
     verify this rule works" recipe in the module docstring.
3. **Confirm it catches the wrong thing.** Deliberately introduce a
   violation in a scratch branch, run `make arch`, observe the failure
   pointing at file:line. Revert. This step is non-negotiable — silent
   rules are worse than no rules.
4. **Give it a non-vacuity floor.** Every walk asserts it found candidates
   (`walked_files(..., minimum=…)`, a count, a named-population check). A guard
   reporting "0 violations in 0 candidates" is indistinguishable from a passing
   one. This has failed for real more than once — most recently a guard whose
   matcher accepted the substring `budget` anywhere in a function, and so stayed
   GREEN when the bound it checked was deleted from the body. Run step 3 against
   **the guard itself**, not only the code it polices.
5. **Register it** in "The current rules" below. Enforced by
   `test_architecture_registry_is_complete.py` — the registry sat at 10 of 34
   guards precisely because this step did not exist, and a partial registry is
   read as the enforced set.
6. **Update CLAUDE.md.** Replace the prose "Never X" rule with a one-liner
   pointer: `Never X — enforced by tests/architecture/test_X.py`.

## Grandfathering an existing violation

The ratchet pattern (Shopify Packwerk): freeze today's violations, fail on
new ones.

**Tach:** run `uv run tach sync`. Tach updates `tach.toml` to allow current
imports. Add a `# GRANDFATHERED: ... retired by <openspec-change-name>`
comment next to the new entry so the retirement path is auditable.

**archon:** add the violating site to the rule's `_ALLOWLIST` constant with
a comment explaining *why* the typed form isn't possible (or "scheduled for
retirement by <backlog entry>"). Allowlist entries are technical debt,
visible and counted.

## Removing a rule

Delete the test file (archon) or constraint (Tach). Update CLAUDE.md to
reflect the new posture. Don't soften a rule — either it's load-bearing
and fails CI, or it isn't and shouldn't pretend to be.

## The current rules

| Rule | Where | Backstops |
|---|---|---|
| Packages may not import from `a2web.<domain>` | `tach.toml` | The microsofware boundary |
| Cross-package imports are explicit (grandfathered) | `tach.toml` | One violation today: `block_detector → escalation` |
| No `json.loads` outside `packages/llm_extract/wobble/` | `tests/architecture/test_json_loads_funnel.py` | Wobble typed funnel (ADR-0001 Pattern 1) |
| No `dict[str, Any]` on slotted dataclasses | `tests/architecture/test_no_dict_str_any_on_dataclasses.py` | Typed pipeline objects > dict bags |
| `@mcp.tool(...)` tools never return `str` | `tests/architecture/test_tools_return_pydantic_not_str.py` | MCP client introspection (matched `@a2kit.read` and ran vacuously through the whole sunset — now matches `@mcp.tool` + asserts a tool-count floor) |
| ~~No `lambda` in `app.provide(...)`~~ | *withdrawn 2026-08-01* | `app.provide` died with a2kit; the guard file does not exist |
| `BaseModel` subclasses at module scope | `tests/architecture/test_response_models_at_module_scope.py` | fastmcp schema generation |
| ~~No stale `TRANSIENT (<change-id>)` marker~~ | *retired 2026-08-01* | Zero `TRANSIENT (` markers existed outside the guard's own source — it enforced a convention with no adopters |

Other rules live alongside the surfaces they govern:

- `tests/architecture/test_boundary_dataclasses_are_frozen.py` — boundary dataclasses under `packages/` are `frozen=True`. It does NOT pin `packages/*/__init__.py` `__all__`; the previous wording here and in CLAUDE.md claimed it did, which is why nobody wrote that check. `__all__` remains deliberately unguarded.
- `tests/architecture/test_aiosqlite_daemon.py` — aiosqlite thread doesn't leak.
- `tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`<!-- gone --> — **withdrawn 2026-08-01: neither the file nor the function exists.** The zendriver backend was promoted to the shelf (`any_browser`) and its fake-fidelity test went with it, but this citation stayed and kept reading as coverage. The standing fake-fidelity contract now has NO instance in a2web, so the failure it was built to catch — the dead `--no-sandbox` rung — is unguarded here. See `docs/architecture/verification-provenance.md`.
- `tests/capabilities/browser_tier/test_browser_gate_policy.py` — the real-launch skip→fail policy; the fail-branch a working browser can never exercise.

### The rest of the registry (completed 2026-08-01)

This table listed **10 of 34** guards for months. The gap was not neglect — there
was no step in the "adding a rule" workflow that said to update it, so every new
guard silently widened the hole, and a reader consulting this file for "what is
enforced" got a wrong answer with authority.

Adding the missing 28 by hand would only reset the clock. The registry's
COMPLETENESS is now mechanized: `test_architecture_registry_is_complete.py`
fails when a guard file is absent from this document. Summaries below are each
guard's own docstring first line.

- `tests/architecture/test_claude_md_citations_resolve.py` — Every path `CLAUDE.md` cites as current actually exists.
- `tests/architecture/test_cold_start_laziness.py` — Cold start: a cheap `query` must construct neither a browser nor an LLM.
- `tests/architecture/test_content_guidance_no_site.py` — Architectural invariant: content guidance is per-KIND, never per-SITE.
- `tests/architecture/test_documented_env_is_real.py` — Configuration the README documents must actually work.
- `tests/architecture/test_eval_not_imported_by_a2web.py` — Architectural invariant: the shipped `a2web` package never imports the.
- `tests/architecture/test_every_hint_code_has_a_factory.py` — Every declared hint code is built by a factory, and every factory lives in one place.
- `tests/architecture/test_fetcher_phase_ordering.py` — The four fetcher orderings that are correct only because of where they sit; written before `decompose-fetcher-into-files` cuts anything, so the move cannot cross one silently.
- `tests/architecture/test_handler_challenge_check.py` — A handler that extracts prose from retrieved HTML must check for a wall.
- `tests/architecture/test_handler_markup_funnel.py` — Architectural invariant: handlers parse markup with a DOM, never a regex.
- `tests/architecture/test_hermetic_llm_env.py` — The suite may not read whether THIS machine has an LLM.
- `tests/architecture/test_json_entity_array_rendering.py` — `structured-entity-array-rendering`: a list-of-dicts entity field (e.g.
- `tests/architecture/test_json_entity_render_is_default_keep.py` — Architectural invariant: JSON-LD entity rendering is default-keep.
- `tests/architecture/test_llm_double_fidelity.py` — Every LLM test double SHALL declare — and prove — what it stands in for.
- `tests/architecture/test_menu_assembly_is_pure.py` — Architectural invariant: the extractor menu collects sources value-blind.
- `tests/architecture/test_no_a2kit_in_specs.py` — The capability specs may not describe the retired a2kit framework.
- `tests/architecture/test_no_local_shelf_source.py` — No shelf dependency resolves to a local working copy.
- `tests/architecture/test_no_personal_strings.py` — The shipping tree carries no operator identifiers.
- `tests/architecture/test_no_rogue_structlog.py` — Architectural invariant: a2web has one logging channel — the `a2web` logger.
- `tests/architecture/test_one_composition_root.py` — There is exactly ONE place a2web builds its object graph.
- `tests/architecture/test_plugin_modules_only_declare_manifest.py` — Architectural invariant: plugin manifest files have no module-level side effects.
- `tests/architecture/test_provider_order_single_source.py` — Architectural invariant: the provider preference order has one source of truth.
- `tests/architecture/test_record_projection_separates_nodes.py` — Architectural invariant: the record-text projection separates DOM nodes.
- `tests/architecture/test_recursive_renderers_are_bounded.py` — Every handler that renders a recursive structure must bound its depth.
- `tests/architecture/test_request_bounds_are_configurable.py` — Every per-request network bound is operator-reachable.
- `tests/architecture/test_spike_scripts_are_runnable_or_archived.py` — A spike script either still runs, or says out loud that it doesn't.
- `tests/architecture/test_tach_covers_every_package.py` — Every package is inside the boundary rule, and every rule has a package.
- `tests/architecture/test_terminal_hint_coherence.py` — Architectural invariant: terminal outcome ↔ operator-hint coherence.
- `tests/architecture/test_trafilatura_funnel.py` — Architectural invariant: HTML extraction is funneled through `content_extract`.
- `tests/architecture/test_transport_discipline.py` — Nothing under `tiers/` or `handlers/` hand-rolls an HTTP client; `zyte`/`firecrawl` are named exceptions with compensating controls (`docs/architecture/transport-discipline.md`).
- `tests/architecture/test_ttl_settings_are_read.py` — Every declared TTL setting is read by at least one code path.
- `tests/architecture/test_walk_is_not_vacuous.py` — The guard on the guards.
- `tests/architecture/test_wobble_policies_match_prompts.py` — The wobble triage agrees with the prompt it claims to be reading.

- `tests/architecture/test_hint_codes_are_declared.py` — Every operator-hint code is drawn from one closed vocabulary.
- `tests/architecture/test_next_links_cap_is_declared_once.py` — No site that builds a `NextLink` holds its own cap literal; the spec's single "capped at 10" invariant has a single implementation (`models.NEXT_LINKS_CAP`). Born when `discourse.py` was found emitting 50 with `handler_probe.py` recording "observed 30" as healthy.

- `tests/architecture/test_tsv_declaration_is_single.py` — The TSV field set is declared once, and both encoders agree with it.

- `tests/architecture/test_response_context_slice.py` — The response builder's slice of `FetchContext` is explicit and bounded.

## Verification provenance — where CI's authority ends

`verification-provenance.md` is the companion to this manual. This README covers
what CI *can* enforce (structural invariants); that doc covers the boundary —
the "green that proves nothing" failure mode (oracle endogeneity), the witness
rule, the three narrow guards that ARE mechanizable, and the honest statement
that independence of a witness cannot be certified by a guard. Read it before
adding a guard whose job is to catch stale prose, permissive fakes, or goldens —
several such guards are theater, and it says which.

## The workflow in one line

> Add a rule = write a test. Land a new violation = it fails CI. Grandfather
> existing violations once; pay them down over time.
