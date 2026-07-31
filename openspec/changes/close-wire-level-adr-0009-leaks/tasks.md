# Tasks

Each group is independently revertible. Within a group, the failing witness
comes before the fix — a witness written after the fix cannot prove it fixed
anything.

## 1. TSV columns lose data on heterogeneous rows

- [x] 1.1 Write a failing test over `content[0].text` (via `call_text`, not
      `call_wire`) asserting a `critical` hint's `severity` survives when an
      `info` hint precedes it. Confirm it fails on current `main`.
- [x] 1.2 Change `wire._derive_columns` to the union of all rows' keys in
      first-seen order.
- [x] 1.3 Assert rows with disjoint keys render empty cells rather than shifting
      values.
- [x] 1.4 Collapse `models._next_links_tsv`, `_other_pages_tsv` and `_links_tsv`
      into the shared rule; delete the three conditional-column bodies.
- [x] 1.5 Re-bless the affected wire contract captures, inspecting each diff
      individually and recording in the commit what moved and why.
      **No existing capture moved.** `query_failure` carries exactly ONE hint
      and it is the critical one, so the first row held every key — the golden
      froze a correct table for the wrong reason and was blind to the defect by
      construction. Added `call/query_heterogeneous_hints` (stale cookie mirror
      + walled page, both hints from the real pipeline) so the shape is now
      frozen. `next_links` gained a permanent `kind` column; `other_pages` is
      byte-identical.
- [x] 1.6 Add a corpus entry for the walled-page-with-preceding-info-hint shape,
      per the never-lose-a-case rule.

## 2. `github.py` launders degradation into ok

- [ ] 2.1 Write a failing test: a supplementary GitHub call raises
      `GitHubException`, and assert the response does NOT present the section as
      empty-at-source.
- [ ] 2.2 Add the unretrieved-section operator hint (decide single-code vs
      per-section per design Open Questions).
- [ ] 2.3 Apply it at all six degrade sites.
- [ ] 2.4 Fix `github.py:226` — widen the README guard from `BadRequest` to
      `GitHubException` so a rate-limited README stops aborting the repo fetch.
- [ ] 2.5 Assert a genuinely-empty section emits no hint.

## 3. `_fetch_old_reddit` returns ok for an interstitial

- [ ] 3.1 Capture a real Reddit block/interstitial page into
      `tests/fixtures/captured/` — captured, never hand-written, per the
      handler-fixture rule.
- [ ] 3.2 Write the failing test: that fixture through `_fetch_old_reddit`
      currently yields `Verdict.ok`.
- [ ] 3.3 Call `challenge_verdict` in `_fetch_old_reddit` before returning.
- [ ] 3.4 Add the architecture guard: every handler path calling a generic prose
      extractor on retrieved HTML also calls `challenge_verdict`.
- [ ] 3.5 Give that guard a non-vacuity floor — assert it found at least the
      three known candidate paths, so a walk matching nothing cannot read green.

## 4. `paid_auth_error` has no hint

- [ ] 4.1 Write the failing test: a paid tier with a bad key produces `failed` +
      `retrieval_incomplete` and NO operator hint.
- [ ] 4.2 Add the hint factory in `models.py` alongside the existing ten.
- [ ] 4.3 Emit it at the paid-tier authentication failure.
- [ ] 4.4 Change `test_terminal_hint_coherence.py:33` from a `None` allowlist
      entry to an assertion that the hint is present, and delete the comment
      that justified the allowlist.

## 5. The `a2effect` taxonomy is unreachable

- [ ] 5.1 Write the failing test: a tool failing for want of an LLM provider
      renders as `UnexpectedDefect`.
- [ ] 5.2 Resolve which `a2effect` class each of the three sites maps to, against
      `a2effect`'s own definitions.
- [ ] 5.3 Re-type `LLMNotAvailable`, `ResourceUnavailable` and the paid auth
      failure.
- [ ] 5.4 Add the standing test that drives the `except AppError` branch, so it
      cannot become unreachable again without a red build.

## 6. Close out

- [ ] 6.1 `make check` green.
- [ ] 6.2 Confirm each of the five witnesses fails when its fix is reverted —
      the fix-reverted check, not merely a green suite.
- [ ] 6.3 Update `CLAUDE.md` if any never-clause wording changed.
- [ ] 6.4 Move the five BACKLOG entries to `BACKLOG-CLOSED.md`.
