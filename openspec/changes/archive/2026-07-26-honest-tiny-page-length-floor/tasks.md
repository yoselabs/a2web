# Tasks

## 0. Confirm invariant-touching design (blocking — Phase A)

- [x] 0.1 Human confirmed the four open decisions in `design.md` (cacheability →
      wire-only/never-cached; confidence → low; similarity → weak robust predicate;
      escalation cap → exactly one). Phase-A gate cleared 2026-07-21. This change
      touches the empty-vs-wall-discrimination first-class invariant.

## 1. Distinguish the bare fallthrough

- [x] 1.1 In `block_detector.py`, make the no-evidence fallthrough (currently the
      bare `length_floor` at :325) distinguishable from a floor violation carrying
      wall/subresource suspicion — a typed marker on the result, not a new verdict
      string on the wire.
- [x] 1.2 Add unit coverage: a short marker-free page yields the bare-fallthrough
      shape; a short page with a wall marker yields the suspicious shape.

## 2. The complete-small-page promotion

- [x] 2.1 Add `is_complete_small_page(observations, url) -> bool` in `actions/empty.py`,
      sharing `has_hard_wall_evidence` / `has_subresource_block_evidence` with
      `is_confirmed_empty`, differing only by dropping the `is_search_shaped` term
      and requiring a corroborating non-empty browser render.
- [x] 2.2 Promotion wired as a flag (`small_page_confirmed`, sibling to
      `empty_confirmed`): `_phase_complete_small_page_promotion` in `fetcher.py` sets
      it after browser corroboration + before extraction; the verdict is LEFT
      `length_floor` (so cache_write declines it and `_confidence_for` yields `low`
      for free), and `build_response` promotes status → ok via `small_page_promoted()`
      only when extraction produced a non-empty answer.
- [x] 2.3 A thin page that is NOT corroborated-complete is unchanged: `content_thin`
      WARNING, body attached, `status: failed` + `retrieval_incomplete: true`.

## 3. Stop the wasted second render

- [x] 3.1 In `playbook.py::_decide_gate_thin_escalate`, cap bare-fallthrough
      `length_floor` browser escalation at 1 (the corroborating witness); a
      wall-suspicious floor violation keeps the existing budget.

## 4. Tests + corpus + docs

- [x] 4.1 Response test: a corroborated tiny complete page (fake HTTP + browser
      both returning the same ~230-char body, no wall) comes back `status: ok`
      with a populated `answer`, not `failed`.
- [x] 4.2 Response test: a thin page WITH wall evidence stays `failed` +
      `content_thin` (the asymmetry holds — no false-positive promotion).
- [x] 4.3 Corpus entry for `example.com` (stable structural fact: a tiny, complete,
      unwalled, non-search page must answer, not fail) so it is a regression guard,
      not a smoke-test footgun.
- [x] 4.4 Update `LESSONS_LEARNED.md` #5 (the length_floor smoke-test footgun) to
      point at the promotion.
- [x] 4.5 `make check` green (1182 passed, coverage 90.38%, arch + lint + ty pass).
      `make bench` NOT run — it is live-network + spends LLM quota and is deliberately
      out of the default gate; gate routing moved, so a bench pass is RECOMMENDED
      before release. The four-axis harness tests (in `make check`) already cover the
      envelope/routing shape and are green.
