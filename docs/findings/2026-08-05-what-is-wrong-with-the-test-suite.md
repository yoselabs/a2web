# What is wrong with the test suite

**Date:** 2026-08-05 · **Measured, not recalled** — every number below has a
command behind it. Companion to
`2026-08-05-what-the-tests-caught-and-what-should-be-substrate.md`, which covers
what *should be shelf substrate*; this one covers **how we own and grow the
suite**, including complaints too small to file separately.

**Relationship to P164** (the prior assessment: *"tests aren't bloated, 1.16:1,
52s; the defect is a missing test→requirement edge"*). That measured **volume**
and found it healthy. This measures **shape**, and finds several things wrong.
Both can be true: the suite is the right *size* and the wrong *shape*. On volume
I mostly agree and say so in §6.

```
  src     142 files   25,750 lines
  tests   260 files   37,007 lines     ratio 1.44 : 1
  runtime 44s, 1743 tests, no test over 3.4s        ← genuinely healthy
```

---

## 1 · The root cause, stated once

**Most tests reach the system through its implementation, not through its
seams.** Everything in §2 is a symptom of this.

| How a test reaches the system | Call sites |
|---|---|
| `make_default_state(...)` — the **sanctioned exception** to single-composition-root | **179** |
| `await fetch(...)` — the orchestrator, directly | 118 |
| `_phase_*` — private pipeline functions | 66 |
| `call_wire(...)` — the MCP wire, structured channel | 23 |
| `mcp_client(...)` — **the documented seam**, a real server over a real client | **15** |
| `make_default_components(...)` — the real composition root | **4** |

CLAUDE.md says: *"`tests/_helpers/mcp.py` is the seam … drives a real
`fastmcp.Client` over the real production server, so nothing about the transport
is faked."* True of 15 call sites out of 1512 test functions. It is not the
seam; it is a seam we use rarely.

And the depth of the reach is measurable:

```
  167 imports of PRIVATE names from a2web, across 77 of 260 test files (30%)
    8  a2web.fetcher._run_extraction_escalation
    6  a2web.tiers.archive._wayback_lookup
    6  a2web.handlers.reddit._parse_atom
    4  a2web.handlers.wikipedia._wikilink_candidates
```

**This is the mechanical cause of the failure that recurred five times this
session** — helper-tested, wiring-untested (the `{{n}}` rehydrator, the archive
dispatch, the deadline observation, the ADR-0014 drift validator, the proxy
breaker classification). A test that imports `_parse_atom` proves `_parse_atom`
works. Nothing then proves anyone *calls* it, or calls it with the right
arguments, or does the right thing with the result. Every one of those five bugs
lived in the gap between a tested helper and its untested call site.

**Why it happened is not laziness.** Reaching through the seam is genuinely
harder: you must construct a plausible page, a plausible tier result, and a
plausible LLM response to test a three-line branch. Importing the private helper
is ten times cheaper and *feels* like the same test. It is not the same test,
and nothing in the repo says so at the moment of writing.

---

## 2 · Structural complaints

### 2.1 · The composition-root rule is enforced everywhere except where it is broken

`test_one_composition_root.py` walks `src/`. CLAUDE.md notes conftest is
*"out of its reach by design"* — the one reviewed exception. In practice the
exception is **179 uses against 4** of the real thing. A rule with a 45:1
exception rate is not a rule with an exception; it is a different rule nobody
wrote down. Worse, it means the graph most tests exercise is `make_default_state`'s
approximation of the graph, so a defect in `build_components` wiring is invisible
to 98% of the suite.

### 2.2 · Guards derive their subject set two different ways, and only one can't silently miss

- **From the filesystem** — `test_tach_covers_every_package.py` asserts the
  declared package list *equals* the real tree. Cannot miss a new package.
- **From a hand-written tuple** — `test_boundary_dataclasses_are_frozen.py`
  parametrizes over `_FROZEN_BOUNDARY_TYPES` with **no completeness assertion**.
  A new frozen boundary dataclass in `packages/` is simply not checked, forever,
  silently.

The repo already invented the fix (`test_architecture_registry_is_complete.py`
does exactly this for the docs index, after finding it listed **10 of 34**
guards). It is applied to two guards and not the others. **This is the
single cheapest structural fix available.**

### 2.3 · Tests are not type-checked

`make ty` runs `ty check src/`. 37,007 lines of test code — the place where
fakes drift out of sync with the real interfaces — get no static checking at
all. Concretely, during §7.2 I had to fix **10 test doubles** (`_FakeFc`, `_Fc`)
by running the suite and reading tracebacks. `dataclasses.replace(parts, …)` was
designed to fail loudly on a stale override; a hand-written fake class has no
such property, and `ty` would have named all ten in one pass.

### 2.4 · Test doubles are copy-pasted, and the copies drift

```
  7×  _FakeFc          4×  _StubProvider
  4×  _FakeSession     4×  _FakeResponse
  3×  _Fc              2×  _FakePage, _FakeHandler
```

Two names (`_FakeFc`, `_Fc`) for the same concept is the tell. Every one of the
ten needed the same edit in §7.2 — ten edits that should have been one. And the
same divergence hit *production* guards: `test_transport_install_chokepoint` and
`test_content_install_chokepoint` are near-identical AST walks written a week
apart, and they already scope assignments differently (one filters by receiver
name, one does not).

### 2.5 · The two-channel lesson is documented and barely applied

CLAUDE.md records the incident: TSV columns derived from `rows[0]` dropped
`critical` from `try_user_browser` — ADR-0009's loudest hint reached the agent
unmarked — and `structured_content` was unaffected, *"which is why ~1350
field-presence assertions missed it."* The stated fix: **when the agent's view is
the point, assert on `call_text`.**

```
  call_wire   23 sites
  call_text    3 sites
```

The lesson is in the docs and in three tests. The default is still the channel
that hid the bug.

### 2.6 · The fixture ratio runs 6:1 against the rule

```
  captured fixtures    8 files
  synthetic fixtures  48 files
```

CLAUDE.md's rule — *"never let a hand-written fixture be the oracle for whether a
parser matches a live site"* — exists because two parsers were found returning
**zero rows** against live pages holding 47 entries and 1066 anchors, behind five
green tests. The rule is right. The corpus is still overwhelmingly the thing the
rule warns about. (Many of the 48 are legitimate: a synthetic fixture that
controls one variable is explicitly allowed. I have not audited which — that is
the actionable item, and it should be audited before the next parser rots.)

### 2.7 · The taxonomy mixes four different axes, and has dead branches

`tests/capabilities/` is 167 files / 25,231 lines — **68% of the suite** — under
25 subdirectories that categorize by:

- **pipeline layer** — `tier_pipeline` (28 files), `extraction`
- **response artifact** — `ask_response`, `fetch_response`
- **invariant** — `retrieval_completeness`, `listing_completeness`
- **module** — `cache`, `app_state`, `app_logging`, `raw_tier`

So there is no answer to *"where does this test go?"* that two people would give
the same way, and no answer to *"what covers ADR-0015?"* without grepping. Plus
actual dead branches: `tests/utils/` is 1 file and **0 lines**;
`tests/plugin_framework/` has **0 files**; `tests/handlers/` holds 1 file / 61
lines while `tests/capabilities/site_handlers/` holds 18 files / 3,461 lines.

### 2.8 · Two naming eras coexist, and only new work uses the good one

`test_fetcher.py` (661 lines) is a grab-bag named after a module — new cases
accrete at the bottom forever. `test_deadline_is_an_unfinished_job.py` is named
after a **claim**, so it has a natural size and an obvious owner. Both styles are
live; new work goes in the new style while the old files keep growing. Nothing
converts them, so the grab-bags are where coverage silently goes to hide (the
deadline path had zero coverage while sitting inside a 661-line file named for
the module that contains it).

### 2.9 · Coverage is a gate, and it is the wrong gauge

`make check` enforces ≥85%; the suite reports **91.93%**. During that same
91.93%:

- the fetch-deadline path had **zero** coverage,
- the never-cache-below-the-gate invariant had **no test at all**,
- inverting the proxy breaker's egress/origin classification passed **1727 of
  1727** tests.

Coverage answers *"was this line executed"*. Every defect this session was a line
that executed and was never *asserted about*. The number is not wrong, it is
answering a question we do not have. It should stay (a floor is better than
nothing) and it should stop being cited as evidence of anything.

### 2.10 · Tach impact analysis would skip exactly the tests that matter

The pytest plugin printed this during my refactor:

```
  [Tach] WARNING: 2 test(s) failed that would be skipped by impact analysis!
```

Those two were the chokepoint guards — the only things that caught the move. It
is currently **opt-in** (`pytest --tach`), so this is a risk rather than a
defect. But the offer on every run is *"~12s could be saved"*, and 12 seconds off
a 44-second suite is not a trade worth the guards. **Recommendation: do not
adopt it, and write down why**, or the offer gets accepted eventually by someone
optimizing a fast suite that was never slow.

---

## 3 · Smaller complaints, and personal ones

**3.1 · I write essays in docstrings and they cannot fail.** 19% of test lines
(7,148 of 37,007) are docstrings. I still defend this — the *why* is the part
that rots fastest and this repo has repeatedly been saved by a comment naming an
incident. But the honest limit: `test_terminal_hint_coherence` carried a
`frozenset({None})` explained by *"paid_auth_error hint emitted at the paid
tier"* — a hint that **did not exist**. The prose was confident, wrong, and
load-bearing. A docstring is not a test, and when the two disagree the docstring
wins in the reader's head. Every essay should end in an assertion that would
fail if the essay were false; several do not.

**3.2 · Guard tests are the highest-value code and the least-owned.** 53 files
in `tests/architecture/`, 5,946 lines, protecting invariants worth more than most
features — and they are written ad-hoc, share one 40-line helper, and duplicate
AST walking machinery in every file. See the shelf proposals in the companion
finding.

**3.3 · `tests/conftest.py` is 321 lines and is a second product.** It holds
`make_default_state`, the sqlite lifecycle leak detector, the hermetic-LLM
scrub. That is real machinery with real invariants and zero tests of its own. If
`_hermetic_llm_env` silently stopped scrubbing, the suite would still be green
and would quietly start billing.

**3.4 · I keep adding a test *file* per bug.** This session: 9 new files. Each
is well-named and well-argued, and the trend is 260 files for 142 source
modules. The alternative — adding a case to an existing suite — is worse when
the existing suite is a 661-line grab-bag, so the file-per-bug habit is a
*symptom* of 2.8, not an independent problem. But nobody is merging them back.

**3.5 · Nothing tells me which invariant a test belongs to.** ADR-0009 is
enforced across at least nine files in six directories. I rebuilt that map by
hand in `2026-08-02-invariant-cell-mapping.md` and it is already stale. A
one-line marker (`@pytest.mark.invariant("ADR-0009")`) would make it a query.

**3.6 · The suite cannot tell me what it does not test.** Every gap this session
was found by mutation — by breaking working code and watching green. That is the
right instrument and it is entirely manual: ~20 mutations, run by hand with
`cp`/`sed`/python, one of which silently applied **zero** occurrences and
reported "All checks passed".

**3.7 · A personal one: the suite made me over-confident twice.** I wrote the
ADR-0014 drift test, watched it pass, and nearly moved on — it passed for the
*wrong reason* (trafilatura strips hrefs, so both URLs were dropped correctly).
Only `diagnostics == []` gave it away. Then `include_routing=True` silently
suppressed the path I was testing, and `debug=False` cleared the diagnostics I
was asserting on. **Three separate ways to write a passing test that tests
nothing, in one sitting.** A green new test deserves the same suspicion as a
green old one.

**3.8 · The test names that read best are the ones I had to argue for.**
`test_breaker_blames_the_egress_not_the_origin`,
`test_incompleteness_is_never_silent`, `test_a_site_answering_badly_never_quarantines_the_proxy`.
Each states a claim a reader can disagree with. `test_fetcher`,
`test_ask_response`, `test_handlers` state a subject, and a subject cannot be
wrong. This is free and we do it half the time.

---

## 4 · Ranked fixes

| # | Fix | Cost | Why this rank |
|---|---|---|---|
| 1 | **Type-check tests** — `ty check src/ tests/` | Hours, plus the backlog it surfaces | Zero design work. Catches the drift class in 2.4 mechanically and forever. |
| 2 | **Completeness assertions on every hand-written guard subject list** (2.2) | Small | The pattern already exists here; it is applied twice out of ~8 opportunities. |
| 3 | **`mutation-probe`** (companion finding, proposal 1) | Medium | Converts the only instrument that finds these defects from manual to repeatable. |
| 4 | **A written rule: a helper test does not count without a wiring test** | Small | Names the root cause at the moment of writing. Five instances this session. |
| 5 | **Invariant markers** (3.5) | Small | Makes "what covers ADR-0009" a query instead of an archaeology project. |
| 6 | **Audit the 48 synthetic fixtures** (2.6) | Medium | The rule exists because this exact corpus hid two dead parsers. |
| 7 | **Retire `tests/utils/`, `tests/plugin_framework/`, fold `tests/handlers/`** | Trivial | Dead taxonomy teaches new tests the wrong home. |
| 8 | **Write down that Tach impact analysis is refused** (2.10) | Trivial | Prevents a future 12-second optimization from disarming the guards. |
| 9 | **Break up `test_fetcher.py` and the other grab-bags** | Large | Real, but it is the symptom; do 1–8 first. |

**Deliberately not proposed:** shrinking the suite. See below.

---

## 5 · What is genuinely good, and should not be touched

- **44 seconds, 1743 tests, nothing over 3.4s.** A suite people actually run.
  Coverage is deliberately kept out of the inner loop; browser tests are opt-in.
  This is the thing most repos get wrong and this one gets right.
- **Guards that name the incident they prevent.** `test_transport_install_chokepoint`
  documents five writers in four orders, one omitting `status_code`. That
  paragraph is why nobody re-adds the sixth.
- **Guards written *before* the refactor they protect.** `test_fetch_context_request_is_frozen`
  was written while the fields were still mutable.
- **The `_walk` non-vacuity floor**, and its own self-check. Born from 30 of 32
  guards passing against an empty tree.
- **Accepted-delta tables that must stay real** — the CLI contract's `_ACCEPTED`
  with `test_every_accepted_delta_is_real`. The correct shape for every
  suppression list in the repo.

## 6 · On volume — where I disagree with the instinct to cut

1.44:1 tests-to-source sounds high and is not the problem. The 5,946 lines of
`tests/architecture/` are worth more per line than anything in `src/`, and the
19% docstring share is mostly incident history that has repeatedly paid for
itself. **The suite is not too big; it is pointed at the wrong places** — deep
into private helpers (§1), shallow at the seams, and gauged by a number that
cannot see the difference (§2.9).

Cutting tests would remove the good ones first, because the bad ones are the
easy-to-write private-helper tests that look busiest.

## 7 · The one number that would change my mind about all of it

`make bench` has not run. Every claim in this document is about whether a2web
*fails correctly*. None of it is evidence that it *answers* better.
