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
4. **Update CLAUDE.md.** Replace the prose "Never X" rule with a one-liner
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
| `@a2kit.read` / `@a2kit.write` tools never return `str` | `tests/architecture/test_tools_return_pydantic_not_str.py` | MCP client introspection |
| No `lambda` in `app.provide(...)` | `tests/architecture/test_no_lambdas_in_app_provide.py` | a2kit v0.36 rejection |
| `BaseModel` subclasses at module scope | `tests/architecture/test_response_models_at_module_scope.py` | fastmcp schema generation |

Other rules live alongside the surfaces they govern:

- `tests/architecture/test_packages_boundary_frozen.py` — `packages/*/__init__.py` `__all__` shapes are pinned.
- `tests/architecture/test_aiosqlite_daemon.py` — aiosqlite thread doesn't leak.

## The workflow in one line

> Add a rule = write a test. Land a new violation = it fails CI. Grandfather
> existing violations once; pay them down over time.
