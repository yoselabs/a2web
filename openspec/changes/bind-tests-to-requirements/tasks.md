## 1. Marker vocabulary

- [x] 1.1 Register the `protects` marker in `pyproject.toml` under
      `[tool.pytest.ini_options] markers`, with a one-line description naming the three
      namespaces (`spec:`, `adr:`, `change:`).
- [x] 1.2 Document the marker in `AGENTS.md` (CLAUDE.md points to it) under Testing —
      the three namespaces, that it is OPTIONAL, and that a named id must resolve.

## 2. Resolution in the reconciler

- [x] 2.1 Extend `scripts/spec_test_reconcile.py` to collect `protects` markers by AST
      parse (not regex) — the marker's arguments are string literals, and a regex over
      test source would also match the marker name inside a docstring or this change's
      own fixtures.
- [x] 2.2 Resolve `spec:<capability>` + heading against `openspec/specs/<capability>/spec.md`,
      matching heading text whitespace-insensitively (design D5). Resolve `adr:<nnnn>`
      against `docs/adr/`, `change:<id>` against `openspec/changes/` (including
      `archive/`).
- [x] 2.3 Report unresolved markers as a distinct section, separate from Column A
      (unlocatable requirements) and Column B (untraceable tests) — an unresolved
      marker is a defect, the other two are a baseline.
- [x] 2.4 Classify a `change:`-cited test as a regression witness in the report, per
      the spec's third scenario. Do not add a separate taxonomy field; the namespace
      IS the classification (design D2).

## 3. The floor

- [x] 3.1 Floor is a literal constant, `TRACEABLE_REQUIREMENTS_FLOOR` in
      `scripts/spec_test_reconcile.py` (not a separate file — an importable sibling
      module under `scripts/` has no `__init__.py`, and a plain module constant with a
      comment satisfies D4 just as well without the import fragility). Set to 1, the
      value measured after seeding (task 5), not copied from the proposal's "4".
- [x] 3.2 `--check` mode added: exits non-zero when the traceable count is below the
      floor, or when any marker fails to resolve. Prints the delta either way.
- [x] 3.3 Reason-on-lowering convention written as a comment directly above the floor
      constant.

## 4. The guard

- [x] 4.1 Added `tests/architecture/test_tests_cite_resolvable_requirements.py`,
      calling `reconcile()` from the reconciler — does not re-implement the parse
      (design D6). Registered in `docs/architecture/README.md`.
- [x] 4.2 Non-vacuity assertion added as its own test
      (`test_the_marker_walk_is_not_vacuous`, minimum 3 markers) — a dedicated test
      rather than folding into `_walk.py`'s idiom, since that helper walks `src/`, not
      `tests/`.
- [x] 4.3 Proved the guard can fail, three times, each reverted after confirming red:
      (a) rewrote the `spec:cache` marker's heading to a nonexistent one → both the
      resolution test and the floor test failed; (b) rewrote an `adr:0002` marker to
      `adr:9999` → the resolution test failed; (c) removed all four seeded markers
      (via `git checkout` on the four files) → the floor test AND the non-vacuity test
      both failed. All three reverted via a saved diff before re-applying.

## 5. Seed citations

- [x] 5.1 Markers added to four tests that already carried the invariant in prose or
      structure, so each marker records an existing fact:
      `test_corroborated_empty_promotes_to_ok` (adr:0017),
      `test_table_columns_are_the_union_of_every_row_not_a_sample` (adr:0002),
      `test_normalize_thread_shapes` (adr:0010),
      `test_no_failing_verdict_reaches_the_cache` (spec:cache).
- [x] 5.2 Six uncited ADRs reviewed. Covered: 0002, 0010, 0017. Explicitly NOT
      covered, with reasons (not an approximate marking): **0006, 0007** are "held,
      not built" ADRs — no implemented behavior exists for a test to cite. **0008**
      (sqlite lifecycle teardown) is an autouse-fixture invariant that spans the whole
      suite, not a claim any single test function makes — no single citation would be
      honest; revisit if the guard becomes an explicit test rather than a fixture.
- [x] 5.3 Floor raised from 0 to 1 (the measured post-seeding count) in this same
      change.

## 6. Wiring and verification

- [x] 6.1 `make arch` needs no new wiring — the guard is a pytest test under
      `tests/architecture/`, already covered by `pytest tests/architecture/ -q`, and
      calls `reconcile()` in-process rather than shelling out (D6). Added
      `make recon-check` as a separate, fast manual/CI entry point
      (`scripts/spec_test_reconcile.py --check`) for checking the floor without going
      through pytest; `make recon` (human-readable) is unchanged.
- [x] 6.2 `ruff check`, `ruff format --check`, and `ty check` pass on every file this
      change touches. Full `make check` was not run clean end-to-end — three
      `tests/architecture/` failures are pre-existing/concurrent (an in-flight
      AGENTS.md/CLAUDE.md rename and unrelated `.beads/issues.jsonl` content),
      confirmed unrelated by isolating this change's files and by `git stash`
      reproducing green at the prior commit. `tests/architecture/` run alone: 173
      passed, 3 pre-existing failures, 0 new failures.
- [x] 6.3 Full suite (`uv run pytest -q`): 36.28s, in line with the 52s baseline
      (baseline included coverage; this run did not — no material regression either
      way).
- [x] 6.4 `Projects/164-test-suite-strategy/strategy.md` (K) updated — Stage 1 and
      Stage 1.5 marked LANDED 2026-08-06, with the floor's starting value (1) and the
      as-shipped marker shape (one `protects` marker, three namespaces, not four
      separate marker spellings).
