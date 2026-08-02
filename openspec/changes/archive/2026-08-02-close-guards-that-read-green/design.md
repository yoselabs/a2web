## Context

Eight guards, all green, none covering what its name claims. Verified 2026-07-31
and re-confirmed while writing this proposal — the AST matcher, the two absent
files, and the zero `pytest_archon` imports were each checked directly.

The pattern is not carelessness. Every one of these was written by someone who
understood the invariant; what failed is that a guard's *population* is invisible
at the call site. `test_handler_markup_funnel` reads as thorough because the
alternative — that `re.compile` is one of five spellings — is not visible from
inside the test.

## Goals / Non-Goals

**Goals**

- Every guard's matcher covers every spelling of what it names.
- Every documented rule resolves to a test that exists.
- The ADR-0009 wire signals cannot be lost by re-blessing a golden.
- A constant that changes product behaviour has a witness that fails when it
  moves.

**Non-Goals**

- Witnessing all ~60 audited constants. Most are genuinely asserted-and-fine.
- Rewriting the corpus. This change makes the judge able to *read*; growing
  coverage is separate.
- Adopting `pytest-archon`. The recommendation is the opposite.

## Decisions

### D1 — Widen the matcher first, fix the violations second

Order matters. Fixing the two reddit regexes first leaves the guard still blind,
and the next one lands green. Widen, watch it go red, then fix — the red run is
the only evidence the widening worked.

Same discipline as `run-the-gate-on-every-push` D-verification: a guard that has
never failed is not known to work.

### D2 — A guard is named for what it asserts, or it is renamed

`test_packages_boundary_frozen` is a *correct* test of dataclass immutability. It
is a *false* citation for `__all__` freezing. Two repairs are available and only
one is honest: rename the test to say immutability, and then decide separately
whether `__all__` needs a guard at all (one package has one).

Do not extend the existing test to cover both. A guard covering two invariants is
how this happened.

### D3 — The citation-resolution guard checks functions, not just files

`test_claude_md_citations_resolve.py` exists and requires a file suffix — which
is why it checks 43 of 78 path-shaped citations and no directory citation at all.
The new guard must resolve `path::function` form, because the zendriver citation
named a function inside a file that also does not exist, and a file-only check
would have caught that one by luck rather than by design.

Widen the existing citation guard's regex to accept directory citations in the
same pass — cheapest fix in the sweep.

### D4 — Lift the ADR-0009 assertions out of the golden, don't harden the golden

Two options: validate `ACCEPT_SLUG` so a blanket re-bless is impossible, or move
the assertions somewhere a re-bless cannot reach.

Do both, but the second is the real fix. A golden proves a surface has not
*changed*; CLAUDE.md already records that it says nothing about whether the
surface was right when captured (`list_tools.json` froze a typo through seventeen
rounds). The ADR-0009 klaxon is a *correctness* claim — `severity == "critical"`
— and correctness claims do not belong in a byte-compare.

Slug validation is still worth having: `wire_harness.py:169` rewrites all 12
goldens on any slug value, so a typo re-blesses the whole set.

### D5 — The constant witness is a behaviour test, not a value assertion

`assert LENGTH_FLOOR == 500` is worthless — it moves with the constant. What
`_HEADING_FRAC_MIN` needs is a captured listing page whose titles are `<div>`s,
asserting records are still detected. That fails at 1.00 and passes at 0.50 for
a reason outside the constant.

This is the same foreign-provenance rule the repo already carries: captured
fixtures, never hand-written ones sized from the thing under test.
`test_wire_content_md.py:17` (`assert len(_PROSE) >= LENGTH_FLOOR`) is the
counter-example to delete.

### D6 — The judge gets the page, and the criteria that cannot be read get retargeted

Two separate repairs, easy to conflate:

- **Wiring:** `replay.py::assert_contract` already supports `status`, exact
  `operator_hints`, `tier`, `next_links_min`, `content_includes/excludes`,
  `input_menu_includes/excludes`. It runs on 7 offline cases. Wiring that same
  vocabulary into the live bench as a per-cell deterministic block turns 33 dead
  criteria live with no new machinery.
- **Semantics:** "does not fabricate" is unanswerable without the source. Pass
  the fetched page to the quality judge.

Note `_NEXT_LINKS_TEMPLATE` currently instructs the one axis that reads URLs to
*"never penalize an entry for being unfamiliar or assume it is fabricated"* —
which directly disarms ADR-0014 checking. That instruction exists because the
judge could not verify; once it can, the instruction inverts.

Also add `retrieval_incomplete` + `narrative` to `replay.py::observe()`. They are
not in the projection today, so the akakce wall baseline cannot regress on them
and is not the second witness it appears to be.

### D7 — Drop `pytest-archon`

Declared, documented as future work in two places, imported nowhere. Every
architecture guard in the repo is hand-rolled `ast` and they work. Removing it
is honest; keeping it is a standing promise that reads as capability.

If the `json.loads` ban is later worth mechanizing, it is ~30 lines of the `ast`
walk this repo already writes fluently.

## Risks / Trade-offs

- **The widened matcher may find more than two violations.** Good, and expected;
  the census that said 18-vs-4 was taken with the narrow matcher. Budget for
  finding a handful more.
- **Replacing reddit's regexes with DOM parsing touches the highest-churn
  handler** (2237 lines of churn, `P(test|src) = 0.73` — the
  fixture-encodes-implementation signature). Check whether those fixtures are
  captured or hand-written *before* trusting them to verify the replacement.
- **A coverage floor will fail runs that pass today.** That is the point, but it
  changes the bench's contract; pick the fraction deliberately and state it.
- **Retargeting corpus criteria is judgement.** 33 criteria addressed to an
  absent reader are not 33 bugs — some should become deterministic assertions,
  some should be deleted as decorative, and telling them apart requires reading
  each.

## Open Questions

- What coverage fraction fails a bench run? 50% of a requested axis is a
  defensible floor; below that the mean is not a measurement. Needs a decision,
  not a default.
- Does `__all__` need a guard at all? One package has one. It may be right to
  delete the citation rather than write the test — but say which, in the docs.
- Should the `playbook.py` foreign witness be a live probe or a replay case? A
  replay case is cheap and offline; a live probe observes real routing. Leaning
  replay, on the grounds that a guard that costs network is a guard that gets
  skipped.
