# Tasks — arch-fitness-functions-bootstrap

Step ordering: tools first, archon rules second, CLAUDE.md cleanup last.

---

## Step 0 — Confirm `wobble-typed-funnel` landed

- [ ] 0a. Verify `src/a2web/packages/llm_extract/wobble/` exists as a folder with `__init__.py`, `_internal.py`, `_policies.py`. If not, finish `wobble-typed-funnel` first.
- [ ] 0b. Confirm `_split_answer_and_routing` no longer calls `json.loads` directly. (`grep -n "json.loads" src/a2web/packages/llm_extract/` should show calls only inside `wobble/`.)

## Step 1 — Install Tach

- [ ] 1a. Add `tach>=0.20,<0.21` to `pyproject.toml` `[tool.uv.dev-dependencies]`.
- [ ] 1b. `uv sync`. Confirm `tach --version` works.
- [ ] 1c. Run `uv run tach mod` interactively to define modules, OR hand-curate `tach.toml` from the explore-session spike. Recommended: hand-curate the initial set (one `[[modules]]` per `packages/X`).
- [ ] 1d. Run `uv run tach sync`. This auto-generates `[[interfaces]]` from each package's `__init__.py` `__all__`, AND emits the grandfather list for existing violations.
- [ ] 1e. Run `uv run tach check`. Expect: green (sync just made it consistent). If red, investigate — the sync may have missed an interface.
- [ ] 1f. Annotate each grandfathered violation in `tach.toml` with a comment: `# retired by <openspec-change-name>`.

## Step 2 — Install pytest-archon

- [ ] 2a. Add `pytest-archon>=0.0.6` to dev-dependencies.
- [ ] 2b. `uv sync`.
- [ ] 2c. Create `tests/architecture/__init__.py` and `tests/architecture/conftest.py` (empty for now).

## Step 3 — Write the five initial archon rules

Each lives in its own `tests/architecture/test_*.py` file. AST-based, not text greps.

- [ ] 3a. **`test_json_loads_funnel.py`** — Walks `src/a2web/packages/llm_extract/`. Asserts no `json.loads` call outside `wobble/`. Acceptance: deliberately introducing a `json.loads` call in `extractor.py` makes the test fail with a precise file:line.
- [ ] 3b. **`test_no_dict_str_any_on_dataclasses.py`** — Walks `@dataclass(slots=True)` classes in `src/a2web/`. Asserts no field's annotation is `dict[str, Any]` or `Dict[str, Any]`. Allowlist constant at the top of the test for known acceptable cases (e.g. `ProviderResponse.raw`).
- [ ] 3c. **`test_tools_return_pydantic_not_str.py`** — Walks `@a2kit.read` and `@a2kit.write` decorated functions. Asserts return annotation is a `BaseModel` subclass, `dict`, or a class-resolved-as-BaseModel (uses `astroid` or string-match — TBD during impl).
- [ ] 3d. **`test_no_lambdas_in_app_provide.py`** — Walks calls to `app.provide(...)`. Asserts the first positional argument is `ast.Name` or `ast.Attribute`, not `ast.Lambda`.
- [ ] 3e. **`test_response_models_at_module_scope.py`** — Walks pydantic `BaseModel` subclasses. Asserts they're defined at module top level (not inside a function or class body).
- [ ] 3f. For each rule, write a **deliberate counter-example test**: a fixture file under `tests/architecture/fixtures/bad_*.py.txt` (not `.py` so it doesn't get imported) and an assertion that the rule walker catches it. Confirms rules don't silently pass.

## Step 4 — Wire into `make check`

- [ ] 4a. Add `arch` target to `Makefile`:
  ```makefile
  arch:
  	uv run tach check
  	uv run pytest tests/architecture/ -v
  ```
- [ ] 4b. Add `arch` to the `check` target dependency list (after `test`, before any "all green" message).
- [ ] 4c. Run `make check` end-to-end. Expect green (Tach grandfathered everything, archon rules pass on current code).

## Step 5 — Retire `tests/test_packages_independence.py`

- [ ] 5a. Confirm Tach's `depends_on = []` on each `packages/X` enforces the same invariant.
- [ ] 5b. Delete `tests/test_packages_independence.py`.
- [ ] 5c. `make check` — green.

## Step 6 — Update CLAUDE.md

- [ ] 6a. Shorten the "Never" list: each rule that's now enforced becomes a one-line pointer to its test file (per design D5).
- [ ] 6b. Add a `## Architecture invariants` section just before "Never" pointing at `tests/architecture/` and `tach.toml`, with a 5-line summary of the workflow ("add a rule = write a test; grandfather existing violations").
- [ ] 6c. Add a `docs/architecture/README.md` describing:
  - When to reach for Tach vs archon
  - How to add a new rule
  - How to grandfather a violation
  - How the ratchet works

## Step 7 — Verify the json.loads ban actually backstops wobble

- [ ] 7a. Deliberately introduce a `json.loads` call in `extractor.py` in a scratch branch. Run `make arch`. Confirm it fails with a precise file:line pointing at the violation.
- [ ] 7b. Revert. Confirm `make arch` green.
- [ ] 7c. Document this acceptance check in `tests/architecture/test_json_loads_funnel.py`'s module docstring as the "how to verify this rule works" recipe.

## Step 8 — Snapshot

- [ ] 8a. `make check` end-to-end green, including the new `arch` gate.
- [ ] 8b. Inspect `tach.toml` and confirm every grandfathered violation has a `# retired by X` comment. If any don't, file a backlog entry per orphan.

---

## Done definition

- [ ] `tach.toml` exists; `make check` includes `tach check` and `pytest tests/architecture/`.
- [ ] Five archon rules live in `tests/architecture/`, each with a counter-example fixture.
- [ ] `tests/test_packages_independence.py` deleted (superseded by Tach).
- [ ] CLAUDE.md "Never" list shortened to pointers + each enforced rule has a test reference.
- [ ] `docs/architecture/README.md` exists.
- [ ] Json.loads ban verified to backstop the wobble funnel via deliberate-violation acceptance check.
- [ ] All grandfathered violations annotated with their retirement path.
