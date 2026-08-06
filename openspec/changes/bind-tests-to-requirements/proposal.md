## Why

Measured 2026-08-05: **4 of 398 requirements are traceable to a test.** 1014
scenarios, 1538 tests, and essentially no edge between them. Two questions the repo
cannot answer today:

- *Which tests do I change to build this feature?* — the route is
  `requirement → scenarios → tests`, and the last arrow does not exist, so the only
  procedure is change-the-code-and-read-the-wreckage.
- *Fifty tests broke. Is the code wrong, or are the tests?* — a test whose oracle is
  the code's own behavior can never report the code is wrong, only that it changed.
  Updating the tests always goes green and always looks correct, silently rewriting
  what the system is promised to do.

`make recon` (landed `19d2d71`) measures the gap. It does not close it. Nothing in
openspec closes it either: `openspec validate --specs --strict` reports 46/46 green
while 23 of 46 capabilities have no capability-named test directory — it validates
document *shape*, never truth, and correctly so. Reconciliation is product-side.

Now, because the gap widens monotonically: +9,970 test LOC in the two weeks to
2026-08-01, and no test has ever been deleted for being subsumed.

## What Changes

- A test MAY declare what it protects, via a marker carrying an identifier that
  already exists elsewhere in the repo — a spec requirement heading, an ADR id, or an
  incident (change) id. No new vocabulary is invented.
- A declared identifier MUST resolve. A marker naming a requirement heading absent
  from `openspec/specs/`, an ADR absent from `docs/adr/`, or a change absent from
  `openspec/changes/` fails the architecture suite.
- The traceable-requirement count is **frozen as a floor that may only rise**. New
  work cannot dilute traceability; existing tests are not backfilled.
- `make recon` gains a `--check` mode asserting the floor, wired into `make arch`.
- **Not** in this change, deliberately: making markers mandatory, spec-delta-as-
  arbiter-of-breakage, requirement budgets, mutation gating, or raising the binding
  depth of existing tests. Those depend on traceability existing first.

## Capabilities

### New Capabilities

- `spec-test-traceability`: a test may name the requirement, invariant, or incident
  it protects; a named identifier resolves or the suite fails; the traceable count is
  a monotone floor.

### Modified Capabilities

None. Adjacent prior art is deliberately left intact rather than absorbed:
`enforcement-integrity` already requires that *a guard* is named and cited for the
invariant it asserts, and that a cited rule resolves to a test function that exists —
that is the same principle applied to the guard population only. This change is its
generalization to all tests and does not subsume it. `test-layout`'s zone rule
governs *where a test lives*; this governs *what a test claims*. Both stand.

## Impact

- `scripts/spec_test_reconcile.py` — gains `--check` and floor persistence.
- `pyproject.toml` — one registered pytest marker (`protects`).
- `tests/architecture/` — one new guard (resolution + floor), with the mandatory
  non-vacuity assertion.
- `Makefile` — `arch` covers the check for free (it's a pytest test); new `recon-check`
  target for a fast manual/CI check outside pytest; `recon` unchanged as the
  human-readable report.
- No production code. No change to `src/`.
- Cost: `make recon` is a text join over 46 specs and 214 test files, sub-second.
