## Why

CLAUDE.md already names this failure twice, and calls it out as the reason for
the anti-vacuity rule:

> Never add a structural guard without an assertion that it found something. A
> guard reporting "0 violations in 0 candidates" is indistinguishable from a
> passing one and reads as coverage while providing none.

The 2026-07-31 sweep found **seven more instances**, all verified by reading the
tests rather than trusting their names. Each was re-confirmed while writing this
proposal:

1. **The markup-funnel guard sees only `re.compile`.**
   `tests/architecture/test_handler_markup_funnel.py:93` and `:128` both match
   `node.func.attr == "compile"`. Every inline `re.search` / `re.sub` /
   `re.match` / `re.findall` is invisible. Two live markup regexes sit inside the
   exact function the guard was written for — `reddit.py:497` (`<!--.*?-->`) and
   `:502` (`<div class="md">(.*)</div>`), whose own comment concedes it depends
   on Reddit never nesting a `<div>`. That is the spelling assumption that killed
   the arXiv and wikipedia parsers on 2026-07-28. The guard's docstring claims a
   clean 18-vs-4 census; **that census counted only `re.compile`.**

2. **`test_packages_boundary_frozen.py` does not test what it is cited for.**
   CLAUDE.md:249 and `docs/architecture/README.md:73` both say it pins
   `packages/*/__init__.py` `__all__`. Verified: it asserts
   `@dataclass(frozen=True)` on `BlockResult` and `EscalationSignal`. The word
   "frozen" is carrying two unrelated invariants. Exactly one package has an
   `__all__` and it is unguarded.

3. **`test_transient_markers_not_stale` has an empty population.**
   `grep -rn "TRANSIENT ("` over `src/` and `tests/` returns 0 outside the guard.
   It cannot fire — while `verification-provenance.md:26` lists it as one of
   three mechanizable remedies.

4. **Two cited guards do not exist.** `test_no_lambdas_in_app_provide.py`
   (`docs/architecture/README.md:15,66`) and
   `tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`
   (`README.md:74`, `verification-provenance.md:70-71`). Both confirmed absent.
   The second is worse than a dead citation: `verification-provenance.md`
   reasons *from its existence* to recommend spending verification effort
   elsewhere. A live budget recommendation resting on a guard that is not there
   — inside the document that codifies the foreign-provenance rule.

5. **`playbook.py` and its test are in 1.00/1.00 lockstep** — 6 commits, neither
   ever moves without the other. 49 of 53 cases restate the table they test.
   Endogenous by construction: same author, same moment, can only confirm the
   two agree. (4 cases *are* independent — two hypothesis property tests,
   uniqueness, purity. Those stay.)

6. **A partial eval loss exits 0.** `broken_axes()` fires only when
   `coverage.scored == 0`. An axis degrading 20/20 → 3/20 is a green run with an
   honest denominator nobody is required to read.

7. **22 constants can be doubled with zero test failures.** Measured by
   rewriting each source literal through a `sys.meta_path` loader. Worst:
   `_HEADING_FRAC_MIN = 0.50` is unwitnessed in **both** directions — at 1.00,
   record detection dies on any listing with non-`<hN>` titles, silently
   removing the ADR-0015 index and the ADR-0009 completeness signal at once.
   `LENGTH_FLOOR = 500` — the single most load-bearing number in the product —
   has an endogenous test: a fixture sized *from* the constant.

And the one with the most leverage:

8. **The corpus cannot see the envelope.** `JUDGE_V1` has three slots and the
   page is not one of them: 21 anti-fabrication criteria are addressed to a
   judge with no ground truth. **33 of 115 criteria** are read by nobody. Nine
   of twelve first-class invariants have **zero** catching cells — ADR-0014,
   ADR-0015, ADR-0017, empty-vs-wall, tier-truthfulness, and the ADR-0009 wire
   half among them. ADR-0012 is the single healthy one, and it is the one with
   no code implementer: witnessed exactly where it is not enforced.

Adjacent, and part of the same picture: **a wire regression on ADR-0009 is one
re-bless from green.** Downgrading the `try_user_browser` hint from `critical` to
`info` — turning the never-silently-miss klaxon into a note for every agent in
the field — fails exactly one test, a golden byte-compare, and
`make bless-wire SLUG=anything` rewrites all 12 goldens without validating the
slug. 55 `retrieval_incomplete` assertions exist; every one reads
`result.<attr>`, never the wire.

**`pytest-archon` is a declared dependency used by zero tests** — verified, zero
imports. ADR-0001 and CLAUDE.md:243 both promise it will close the `json.loads`
loop. An auditor sees an installed library and a promise.

Why now: this change is worth little until `run-the-gate-on-every-push` lands —
a guard that does not run on push cannot be improved into one that does. Sequence
it immediately after.

## What Changes

- **Widen the markup-funnel AST matcher** to `search` / `sub` / `match` /
  `findall`, then fix the two reddit patterns it exposes. Re-run the 18-vs-4
  census against the widened matcher and correct the docstring's claim.
- **Split the "frozen" conflation.** Keep the dataclass-immutability guard under
  a name that says so; add a real `__all__` guard, or delete the citation. Do not
  leave one test answering for two documented invariants.
- **Retire or populate `test_transient_markers_not_stale`.** A guard over an
  empty population is removed and its absence recorded, per
  `enforcement-integrity`.
- **Fix the two dead citations**, and add a guard that every architecture rule
  cited in `docs/architecture/README.md` and `verification-provenance.md`
  resolves to a file *and a test function* that exists.
- **Give `playbook.py` a foreign witness** — an outcome-level case (corpus or
  replay) where the *result* of a routing decision is observed, not the decision
  restated.
- **Add an eval coverage floor** — a requested axis scoring below a stated
  fraction fails the run rather than reporting a smaller denominator.
- **Witness the load-bearing constants.** Not all 22: `_HEADING_FRAC_MIN`,
  `_CONSISTENCY_MIN`, `LENGTH_FLOOR`, and the four silent truncation caps are the
  set that changes product behaviour. Port arXiv's `N of M` shortfall pattern to
  `habr`, `hn`, `v2ex`, `discourse`.
- **Wire the replay assertion vocabulary into the live bench**, so the 33 dead
  criteria become executable, and pass the fetched page to the quality judge so
  "does not fabricate" is checkable at all.
- **Lift the ADR-0009 wire assertions out of the golden**, into a standalone
  capability test asserting all five signals plus `severity == "critical"`, so a
  re-bless cannot launder them. Validate `ACCEPT_SLUG` against the known set.
- **Either use `pytest-archon` or drop it.** Recommend dropping: every guard here
  is hand-rolled `ast` and works.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `test-fidelity`: a structural guard SHALL match every call form of the
  construct it names, and its stated census SHALL have been taken with the
  matcher that ships.
- `enforcement-integrity`: every architecture rule cited in the documentation
  SHALL resolve to an existing test; a guard SHALL be named for the invariant it
  actually asserts.
- `eval-measurement-integrity`: a partial loss on a requested axis SHALL fail the
  run below a stated coverage floor.
- `eval-corpus`: the judge SHALL be able to read what it is asked to score;
  criteria addressed to an absent reader SHALL be removed or wired.

## Impact

- `tests/architecture/` — matcher widened; two guards renamed or retired; one
  citation-resolution guard added
- `src/a2web/handlers/reddit.py` — two markup regexes replaced with DOM parsing
- `src/a2web/handlers/{habr,hn,v2ex,discourse}.py` — shortfall declaration
- `src/a2web/llm_eval/` — coverage floor; judge gets the page
- `tests/contracts/wire/` — ADR-0009 assertions lifted out of the golden path
- `eval/corpus.yaml` — criteria retargeted at readers that exist
- `pyproject.toml` — `pytest-archon` removed
- `docs/architecture/README.md`, `docs/architecture/verification-provenance.md`,
  `CLAUDE.md` — citations corrected; the provenance doc records that it failed
  its own rule

## Out of Scope

- The remaining ~15 unwitnessed constants. Recorded in `BACKLOG.md`; only the
  behaviour-changing ones are in this change.
- Corpus language coverage (English 26 / Turkish 9 / Russian 1 / Chinese 1 —
  every wall, commerce, empty-vs-wall and 404 case is Turkish). Real, and its own
  change.
- Re-measuring `models.py ↔ tests/contracts/wire/` co-change. The pre-sunset
  golden was deleted; its replacement has 5 commits of history. Re-measure in a
  month.
