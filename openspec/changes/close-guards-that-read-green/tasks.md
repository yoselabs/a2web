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

- [ ] 4.1 Add an outcome-level witness for `actions/playbook.py` — a replay or
      corpus case where the *result* of a routing decision is observed, not the
      decision restated. Prefer replay (offline, always runs).
- [ ] 4.2 Keep the four genuinely independent cases in `test_decide_next.py`
      (`:52`, `:59` hypothesis properties; `:518` uniqueness; `:526` purity).
      The other 49 restate the table and can stay as documentation, but must not
      be counted as verification.

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
- [ ] 5.6 Record the remaining unwitnessed constants in `BACKLOG.md` rather than
      widening this change.

## 6. The corpus can see the envelope

**NOT STARTED.** This group is bench-side and its verification step is a live
`make bench` run — network + LLM quota under ADR-0016, not something to spend
unasked. §6.4 alone ("walk the 33 unread criteria, each becomes a deterministic
assertion or is deleted as decorative — do not bulk-convert") is a careful
read-each-one pass. Left for a session that can run the bench and check the
result.

- [ ] 6.1 Pass the fetched page to the quality judge. `JUDGE_V1`'s three slots
      (`{ask}`, `{content}` = criteria, `{answer}`) do not include it.
- [ ] 6.2 Wire `replay.py::assert_contract`'s vocabulary (`status`,
      `operator_hints`, `tier`, `next_links_min`, `content_includes/excludes`,
      `input_menu_includes/excludes`) into the live bench as a per-cell
      deterministic block.
- [ ] 6.3 Add `retrieval_incomplete` and `narrative` to `replay.py::observe()`.
      They are not in the projection, so the akakce wall baseline cannot regress
      on them today.
- [ ] 6.4 Walk the 33 unread criteria. Each becomes a deterministic assertion, or
      is deleted as decorative. Do not bulk-convert — telling them apart requires
      reading each.
- [ ] 6.5 Invert `_NEXT_LINKS_TEMPLATE`'s *"never penalize an entry for being
      unfamiliar or assume it is fabricated"*. That instruction exists because
      the judge could not verify; once it can, it disarms ADR-0014.
- [ ] 6.6 Produce the invariant → catching-cell mapping and record the gaps. Nine
      of twelve currently have zero cells.

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
- [ ] 8.4 Move the shipped T4 entries to `BACKLOG-CLOSED.md`; leave the deferred
      constants and corpus-language entries open.
