## Context

`make recon` (`19d2d71`) measures the spec↔test gap: **4 of 398 requirements traceable
to a test**, 1014 scenarios, 1538 tests, 13/18 ADRs cited. Full suite runs in 52s, so
this is not a performance problem — it is a legibility and decidability problem.

Two prior facts constrain the design.

**openspec will not close this and should not.** `openspec validate --specs --strict`
returns 46/46 green while 23 of 46 capabilities have no capability-named test
directory. It validates document shape. Deciding whether a scenario still holds
requires knowing what the code does, which is a different tool class. Reconciliation
is product-side — and this repo already has the idiom, 50 architecture tests doing
AST/text joins.

**The spec is not append-only, but staleness is undetected.** 26 of 136 archived
changes carry a `REMOVED Requirement`; `test-fidelity` even propagates subsumption
down to "that point fix SHALL be deleted." So 398 is already net of pruning. What is
missing is *detection*: removal fires only when an author already knows a requirement
died. A requirement invalidated as a side effect of other work persists silently.

Analysis and measurements: `Projects/164-test-suite-strategy` (K).

## Goals / Non-Goals

**Goals:**

- Make *which tests protect this requirement* answerable by grep, for new work.
- Make a renamed or removed requirement surface the tests that described the old
  behavior, instead of leaving them green and orphaned.
- Freeze traceability as a monotone floor so the gap stops widening.
- Cost nothing on the common path — no production code, no runtime change.

**Non-Goals:**

- Mandatory markers. 1,534 existing tests would fail on the first run.
- Backfilling existing tests. Ratchet forward only.
- Spec-delta-as-arbiter-of-breakage (the rule that a spec-marked test may not be
  edited in a change carrying no spec delta). Depends on traceability existing first.
- Requirement budgets, mutation gating, raising binding depth to the wire.
- Deleting any test. Runtime is 52s; field practice (Microsoft/THEO, Google) is
  throttle execution, never shrink the corpus. Deletion is only ever justified by
  subsumption, never by volume.

## Decisions

### D1 — A pytest marker, not a docstring convention or a naming scheme

`@pytest.mark.protects("spec:<capability>", "Requirement: <heading>")`.

*Why:* markers are structured, registered in `pyproject.toml`, introspectable without
parsing source, and already how this repo selects tests (`-m browser`). A future
`pytest -m 'protects'` selection falls out for free.

*Alternatives:* docstring convention (unstructured, drifts, needs a parser);
directory-per-requirement (398 directories, and a test can legitimately protect more
than one requirement); test-name encoding (unreadable, and headings contain spaces).

### D2 — The marker carries an existing identifier, never a new one

Three namespaces, all pre-existing: `spec:<capability>` + requirement heading,
`adr:<nnnn>`, `change:<change-id>`.

*Why:* the design constraint is that placement be **decidable at write time without
reading the rest of the suite**. An agent cannot perform subsumption spontaneously —
that needs 1,534 tests in context — but it can copy an id it is already holding. The
evidence says it will: ADR ids already appear unprompted in 90 test files across 15
ADRs. This is a missing-vocabulary problem, not a discipline problem.

*Alternative rejected:* a hand-authored taxonomy (`behavior`/`invariant`/`guard`/
`witness`). Requires a judgment call per test, so an agent guesses, so it decays. The
population falls out of *which namespace* was cited instead — `change:` is a
regression witness by construction.

### D3 — Optional marker, monotone floor

The obligation constrains the *direction of travel*, not the current position.

*Why:* a mandatory marker fails 1,534 tests on day one and gets disabled. The floor
technique is already native here — the coverage floor set just below measured, the
CLI contract's `_ACCEPTED` delta table. Same shape, same reason.

### D4 — The floor is a committed literal, not computed

*Why:* a floor derived from the suite it constrains can only report that the suite
equals itself. This repo has been bitten by exactly this class — guards that read
green while checking nothing. Pair with the mandatory non-vacuity assertion.

### D5 — Heading match is whitespace-insensitive, but otherwise exact

*Why:* reformatting a spec (rewrapping a line) must not break citations; renaming a
requirement MUST break them, because that is the signal — the rename should surface
every test that described the old behavior. Choosing exactness here is choosing which
edits are loud.

### D6 — `--check` extends the existing script; the guard is a thin architecture test

*Why:* one implementation of the join, two consumers (human report, CI assertion). A
separate guard re-implementing the parse is how the two come to disagree.

### D7 — `enforcement-integrity` is generalized, not absorbed

It already requires that *a guard* is named and cited for the invariant it asserts,
and that a cited rule resolves to a test function that exists. That is this principle
applied to the guard population. This change extends it to all tests and leaves it
standing.

*Why:* "never let a later stage discard a producer's own claim" — the repo's
recurring defect, four times in one week. A broader requirement that silently
swallows a narrower one is the same move. If it should be subsumed, that is a
deliberate `REMOVED Requirement` in a later change, with a reason.

## Risks / Trade-offs

**Goodhart: markers get written to satisfy the checker, and specs get written to
justify markers.** → The floor counts *requirements traceable*, not *tests marked*, so
adding markers to already-traceable requirements scores nothing. Promotion of a test
into a new spec requirement stays a reviewed act inside a change; it is not something
the check can reward. This is the main risk in the whole strategy and it is not fully
mitigated by this change alone — the requirement budget that completes the mitigation
is deliberately out of scope here.

**A citation asserts a relationship nothing verifies.** A test may cite a requirement
it does not actually exercise. → Accepted. Resolution is checkable; relevance is not,
short of mutation analysis per (requirement, test) pair. A wrong-but-resolving
citation is still strictly better than none: it is greppable, reviewable, and breaks
loudly on rename.

**Optional markers may simply not get used.** → The floor makes non-use visible as a
flat number over time rather than as silence. If it stays flat for a month, the
write-time rule failed and the answer is the harder Stage 2 gate, not more prompting.

**One more thing to keep current.** → Cost is bounded: sub-second text join, no
production code, no `make check` runtime change beyond one guard.

## Migration Plan

Additive; nothing to migrate. Rollback is deleting the guard and the marker
registration — no test changes shape, no production code is touched.

Initial floor is set to the measured value at implementation time (4 at the time of
writing; re-measure, do not hardcode this number from the proposal).

## Open Questions

- **Requirement or scenario granularity?** Requirement is more stable under spec
  edits; scenario is more precise. Chosen: requirement. Revisit if requirements prove
  too coarse to locate tests usefully.
- **Does citation change agent behavior on a breakage, or is the hard Stage 2 rule
  required?** Testable: run one change under each regime. Not resolved here.
- **Is `ask-response` (37 req / 96 scen / 89 tests / 0 cited) honest?** A spot-audit
  determines whether the spec is worth binding to before investing further. Deferred,
  not answered by this change.
