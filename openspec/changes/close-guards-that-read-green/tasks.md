# Tasks

Sequence after `run-the-gate-on-every-push`. Improving a guard that does not run
on push buys nothing until it does.

## 1. The markup funnel

- [x] 1.1 Widen the AST matcher in `tests/architecture/test_handler_markup_funnel.py`
      (`:93`, `:128`) from `compile` to `compile`/`search`/`sub`/`match`/`findall`.
- [x] 1.2 Run it and record what goes red. Expect at least `reddit.py:497` and
      `:502`; budget for more. **Do not fix anything yet** — the red run is the
      only evidence the widening works.
- [x] 1.3 Replace `reddit.py:497` (`<!--.*?-->`) and `:502`
      (`<div class="md">(.*)</div>`) with `dom_schema.extract`. Note `:500-501`'s
      own comment concedes the nesting assumption.
- [x] 1.4 Before trusting the reddit fixtures to verify the replacement, check
      whether they are under `tests/fixtures/captured/` or hand-written.
      `P(test|src) = 0.73` is the fixture-encodes-implementation signature.
- [x] 1.5 Re-take the 18-vs-4 census with the shipped matcher and correct the
      guard's docstring claim.
- [x] 1.6 Fix any further violations the widening exposed.

## 2. Guards named for what they assert

- [x] 2.1 Rename `test_packages_boundary_frozen.py` to name dataclass
      immutability, which is what it asserts.
- [x] 2.2 Decide whether `packages/*/__init__.py` `__all__` needs a guard (one
      package has an `__all__`). Write it, or withdraw the citation — say which
      in the docs.
- [x] 2.3 Correct CLAUDE.md:249 and `docs/architecture/README.md:73`.
- [x] 2.4 Retire `test_transient_markers_not_stale` — zero `TRANSIENT (` markers
      exist outside the guard. Record the retirement and remove it from
      `verification-provenance.md:26`'s list of three mechanizable remedies.

## 3. Citations that resolve

- [x] 3.1 Remove `test_no_lambdas_in_app_provide.py` from
      `docs/architecture/README.md:15,66` — `app.provide` died with a2kit.
- [x] 3.2 Correct `docs/architecture/README.md:74` and
      `verification-provenance.md:70-71`, which cite
      `tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`.
      Neither file nor function exists.
- [x] 3.3 **Re-examine `verification-provenance.md`'s budget recommendation.** It
      reasons from that guard's existence to advise spending effort elsewhere.
      With the guard absent, the conclusion needs re-deriving, and the failure it
      was built to catch (the dead `--no-sandbox` rung, cited twice in the same
      file) is currently unguarded.
- [x] 3.4 Record in `verification-provenance.md` itself that the document
      codifying the foreign-provenance rule failed it. That belongs in the doc,
      not only in a fix.
- [x] 3.5 Add a citation-resolution guard covering `path::function` form and
      directory citations, across CLAUDE.md, `README.md`, and
      `verification-provenance.md`.
- [x] 3.6 Widen `test_claude_md_citations_resolve.py:61`'s file-suffix regex so
      directory citations are checked. Fix the citations it exposes —
      CLAUDE.md:29 and :81 both point at changes that moved under `archive/`.
- [x] 3.7 Fill in the rules registry: `docs/architecture/README.md` lists 10 of
      33 guards. Add a step for it to the documented "adding a rule" workflow —
      its absence is why the table rotted.

## 4. The playbook's foreign witness

**NOT STARTED.** 4.1 wants a replay or corpus case observing the RESULT of a
routing decision rather than restating it — that is new offline replay
infrastructure, not a tweak, and it is the group most likely to be done badly if
rushed at the end of a long session.

- [x] 4.1 **Shipped as the `steps` contract key** — the ordered `tier:verdict`
      sequence a fetch actually dispatched, projected by `replay.py::observe()`
      from the real orchestrator over frozen bytes and blessed on all seven
      baselines. Nothing in the corpus names a rule, so it cannot agree with the
      planner by construction. **Coverage measured, and it is thin:** deleting
      `cloudflare_403_429_archive` fails the akakce baseline; deleting
      `paywall_or_block_archive`, `exhausted_429_escalate` or
      `gate_browser_signal` fails NOTHING. 1 of 4 probed, of fourteen rules —
      the corpus is mostly happy paths and a planner witness needs cases that
      fail interestingly. Gap recorded in `BACKLOG.md` rather than overstated.
- [x] 4.2 The four independent cases are named in `test_decide_next.py`'s
      docstring, which now states plainly that the rest re-encode the table they
      check — a rule written wrong and a case written from the same
      understanding agree, both go green, and the pair reads as proof. Kept (they
      catch a deletion or a typo) and pointed at the foreign witness.

## 5. Constants that change behaviour

**5.4/5.5 SHIPPED 2026-08-01.** 5.1/5.2/5.3 remain open — each needs a CAPTURED
page with a specific property (item titles in `<div>`/`<span>`; mixed
sponsored/promoted card types; a real page straddling `LENGTH_FLOOR`). Writing
those fixtures by hand would reproduce the exact defect the tasks exist to fix:
a fixture authored beside the constant cannot falsify it. Recorded in BACKLOG
per 5.6 rather than faked.

- [ ] 5.1 `_HEADING_FRAC_MIN` (`detector.py:62`) — add a captured listing page
      whose item titles are `<div>`/`<span>`, asserting records are still
      detected. It must fail at 1.00.
- [ ] 5.2 `_CONSISTENCY_MIN` — same shape; a listing with mixed card types
      (sponsored/promoted rows) must still detect.
- [ ] 5.3 `LENGTH_FLOOR` — delete `tests/capabilities/extraction/test_wire_content_md.py:17`
      (`assert len(_PROSE) >= LENGTH_FLOOR`, a fixture sized from the constant)
      and replace with a captured-page behavioural witness.
- [x] 5.4 Port arXiv's `N of M` shortfall declaration (`arxiv.py:297`) to
      `habr._MAX_COMMENTS`, `hn._ALGOLIA_SEARCH_HITS_PER_PAGE` (Algolia returns
      `nbHits`, currently ignored), `v2ex._MAX_REPLIES`, `discourse._MAX_TOPICS`.
      `hn` and `v2ex` already hold the total.
- [x] 5.5 Propagate the zyte timeout correction to `firecrawl._TIMEOUT_S = 40.0`
      — zyte's identical 40.0 was measured to fail under concurrent load
      (`2bf60ca`) and raised to 60; firecrawl kept 40 and still carries the
      falsified "generous headroom" comment.
- [x] 5.6 Recorded — the `2026-08-01 — deferred from close-guards-that-read-green`
      entry names all three with the specific captured page each needs, and says
      why hand-writing them reproduces the defect. Updated 2026-08-02 to strike
      the §4/§6 items that have since shipped.

## 6. The corpus can see the envelope

**NOT STARTED.** This group is bench-side and its verification step is a live
`make bench` run — network + LLM quota under ADR-0016, not something to spend
unasked. §6.4 alone ("walk the 33 unread criteria, each becomes a deterministic
assertion or is deleted as decorative — do not bulk-convert") is a careful
read-each-one pass. Left for a session that can run the bench and check the
result.

- [ ] 6.1 Pass the fetched page to the quality judge. `JUDGE_V1`'s three slots
      (`{ask}`, `{content}` = criteria, `{answer}`) do not include it.
- [x] 6.2 Wire `replay.py::assert_contract`'s vocabulary (`status`,
      `operator_hints`, `tier`, `next_links_min`, `content_includes/excludes`,
      `input_menu_includes/excludes`) into the live bench as a per-cell
      deterministic block. **Done 2026-08-02.**

      The checker moved to `src/a2web/llm_eval/case_contract.py` and BOTH
      harnesses now call it — `replay.assert_contract` was rewritten to consume
      it, so there is one implementation rather than a copy that would drift.
      (`src/` importing from `tests/` was the alternative and is backwards.)
      Corpus entries take an optional `contract:` block in the same vocabulary;
      `datadome-wall-commerce` is pinned as the first case, converting four
      facts it already KNEW (`status: failed`, `retrieval_incomplete`,
      `narrative_present`, `answer_present: false`) from prose criteria a judge
      scored probabilistically into deterministic per-cell assertions.

      **The load-bearing decision is the third outcome.** The live bench cannot
      observe `steps` or `input_menu_*` — those come from the cassette spy — so
      `check_contract_keys` returns `(failures, unsupported)` and the bench
      records an UNOBSERVABLE reason rather than a pass. Collapsing "I could not
      check this" into "this passed" is the precise failure this whole change
      exists to close, and it would have been the easy implementation.

      An unknown key is a FAILURE, not a skip: a typo must not read as a
      silently-absent assertion.

      Tested at the seam, not just the comparisons: every key is exercised in
      its FAILING direction (a vocabulary only ever tested passing is
      indistinguishable from one wired to nothing), the replay-only split is
      asserted to be a real non-empty proper subset, and the two projections are
      asserted to use the same key names — if one renames a key its assertions
      silently stop running, and that test is what notices.

      Not verified by a live bench run: the axis is deterministic and offline-
      testable, and a $10 run to watch one boolean is not the way to check it.
      `make check`: 1550 passed.
- [x] 6.3 Both in the projection, plus `narrative_present` and a
      `narrative_includes` intent key; blessed unconditionally on any non-ok
      status (a truthy gate would drop the key from the baseline exactly when the
      signal went missing, taking its own assertion with it). akakce now pins
      `retrieval_incomplete: true` + `narrative_present: true`. **Finding:**
      `narrative` embeds real wall-clock durations ("raw → ok (8ms)"), so it was
      the one projection field not deterministic from frozen bytes — caught
      immediately by `test_selftest_replay_is_reproducible` and scrubbed via
      `_DURATION_RE`, the same treatment `fetched_at` already had.
- [x] 6.4 Walked all 142 criteria across 44 cases. **Done 2026-08-02.**

      Four outcomes, not two — the task said "assertion or deleted" and the
      reading produced a third and fourth that matter more:

      **Converted (23 criteria → 16 cases carrying a `contract:` block).**
      Needed 15 new vocabulary keys; §6.2 shipped only the eight replay already
      had, and none of them can say what most dead criteria are about. Sharpest:
      `operator_hints_exclude` — *"never fire `try_user_browser` on a 404"* is
      ADR-0009's most specific negative claim, appears in three cases, and had
      no expression at all.

      **Kept as prose (~20).** Anti-fabrication criteria ("does not invent a
      review quote", ADR-0014 traceability) need the FETCHED PAGE, which no
      harness passes to any reader. They are not convertible and not decorative
      — they are §6.1's blocked scope, and deleting them would erase the record
      of what is unguarded. Recorded, not converted.

      **Deleted as decorative (3).** Each asserted a property of a2web's CODE
      rather than of this cell's output: "fence tolerance is never removed",
      "a degraded run should score worse", "wall detection does not depend on
      Cloudflare markers". A judge reading one answer cannot evaluate any of
      them, and no run ever could.

      **RETARGETED (1) — and this is the finding.**
      `fetch-deadline-reports-an-unfinished-job` asserts expired-budget
      behaviour (`status: failed`, a critical `fetch_deadline_exceeded` hint)
      against a bench run using the NORMAL budget on a Wikipedia article that
      fetches healthily. Four of its five criteria were scored against the
      opposite of what the bench produces — on every system, on every run,
      since the case landed. Not a weak signal: a wrong one, dragging the
      quality mean down. Its own comment conceded it ("exercise by setting
      A2WEB_FETCH_DEADLINE_S very low") and the corpus has no per-case env.
      The expiry half is genuinely covered by
      `tests/capabilities/tier_pipeline/test_fetch_deadline.py`; the case now
      asserts the half no unit test does — that the deadline must NOT fire on
      healthy work.

      **Comparability cost, stated rather than absorbed:** converting means
      DELETING the criterion, which changes those cases' quality scores against
      the 2026-08-02 baseline. Correct here — an unreadable criterion produced
      a noise score, not a signal — but it is the same objection raised against
      6.1, so it is named, not hidden.

      Two guards close the loop offline, both reversion-probed:
      `test_every_shipped_contract_key_is_in_the_vocabulary` (a typo used to
      cost a $10 run to discover) and
      `test_shipped_per_row_keys_are_paired_with_a_floor` (a per-row predicate
      is vacuously true over an index that vanished — the exact shape this
      change exists to close, reproduced inside it).

      Not verified by a live run. `make check`: 1572 passed.
- [ ] 6.5 Invert `_NEXT_LINKS_TEMPLATE`'s *"never penalize an entry for being
      unfamiliar or assume it is fabricated"*. That instruction exists because
      the judge could not verify; once it can, it disarms ADR-0014.
      **NOT DONE 2026-08-01, deliberately — the premise does not hold.** The
      judge receives the task string and the rendered block and nothing else,
      so it still cannot verify; telling a blind judge to suspect fabrication
      buys guesses, not verification. ADR-0014 is a DETERMINISTIC property
      (every emitted URL traceable to an anchor on the fetched page) and belongs
      in a check that can read the page, not in an LLM opinion. The prompt WAS
      rewritten in the same pass for a different, measured defect — it was
      penalising faithfully-relayed items and so rewarding ADR-0012 violations.
- [x] 6.6 `docs/findings/2026-08-02-invariant-cell-mapping.md`. **Done 2026-08-02.**

      **9 of 12 with zero catching cells → 4.** Named cells per invariant, not
      counts, and split three ways rather than covered/not: **D**
      deterministic (a contract key, definitively falsifiable), **J** judged
      (readable from the answer prose), **∅** unreadable (the judge cannot see
      its subject — it can never fail). The ∅ tier is why §6.4 kept ~20
      criteria rather than deleting them: they are the standing record of what
      is unguarded, and this table is what they are for.

      ADR-0015 went 0 → 7, the largest move, and for a structural reason: it is
      an invariant about a SHAPE (`other_pages`/`options`/`also_here`
      non-empty), which is exactly what a deterministic key asserts and a prose
      judge cannot.

      **The honest zero is ADR-0014** — 7 criteria, 6 cases, not one can fail.
      But it does not need §6.1's judge: "is every emitted URL in the page's
      anchor set" is deterministic set membership, so it belongs in a contract
      key. Cheaper than 6.1 and now the highest-value item left here.

      **never-cache-below-the-gate has no cell and no plan** — neither harness
      observes the cache. Needs a projection field first; recorded, not faked.

      **And §4.1 / §6.3 were claims about the CODE, not the corpus.** §4.1 said
      `steps` was "blessed on all seven baselines"; §6.3 said akakce pinned
      `retrieval_incomplete` + `narrative_present`. Measured: **2 of 8
      baselines carried neither** — including `zoro-datadome-bot-wall`, the
      canonical wall specimen and the ONLY offline cell ADR-0009's wire half
      depends on. The bless code was right; the baselines were never re-blessed
      after the case split, and nothing failed because the assertions simply
      did not exist. Fixed by one `A2WEB_BLESS_EVAL=1` run; verified by
      flipping `retrieval_incomplete` to false and confirming red.

## 7. The ADR-0009 wire signals

- [x] 7.1 Lift the three inline asserts out of `test_wire_query_failure` into a
      standalone wire capability test asserting all five signals **plus**
      `severity == "critical"`.
- [x] 7.2 Verify by downgrading the hint in the wire projection and confirming
      the new test fails independently of any golden.
- [x] 7.3 Validate `ACCEPT_SLUG` in `wire_harness.py:169` against the known set —
      today any value rewrites all 12 goldens.
- [x] 7.4 Note in the wire-contract docs that `test_no_golden_is_degenerate` bars
      only `len(text) > 20`; the real coverage is the inline per-scenario
      asserts.

## 8. Close out

- [x] 8.1 Remove `pytest-archon` from `pyproject.toml:223-226`. Correct
      ADR-0001:60 and CLAUDE.md:243 to state the `json.loads` loop as open.
- [x] 8.2 Extend `test_json_loads_funnel.py:30`'s walked root, or record the gap:
      two of the five named LLM-contract-parsing sites (`llm_eval/bench_judge.py`,
      `fetcher_response.py::_project_routing`) live outside it.
- [x] 8.3 `make check` green, and confirm each widened or added guard has been
      observed failing at least once.
- [x] 8.4 Moved the five shipped T4 findings (markup funnel, two mis-named
      guards, two non-existent cited guards, the ADR-0009 wire re-bless, the
      playbook lockstep). **Left open, correctly:** *22 constants can be doubled*
      (§5.1-5.3, capture-bound), *the corpus cannot see the envelope* (§6,
      bench-side), *invariants with no code implementer* (§6.6), plus two T4
      findings this change never scoped — *a partial eval loss exits 0* and *45
      of 86 prompt rules have neither code nor test*.
