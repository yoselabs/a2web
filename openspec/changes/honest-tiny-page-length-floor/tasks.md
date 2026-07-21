# Tasks

## 0. Confirm invariant-touching design (blocking — Phase A)

- [ ] 0.1 Human confirms the four open decisions in `design.md` (cacheability,
      confidence tier, similarity predicate, escalation cap) before implementation.
      This change touches the empty-vs-wall-discrimination first-class invariant.

## 1. Distinguish the bare fallthrough

- [ ] 1.1 In `block_detector.py`, make the no-evidence fallthrough (currently the
      bare `length_floor` at :325) distinguishable from a floor violation carrying
      wall/subresource suspicion — a typed marker on the result, not a new verdict
      string on the wire.
- [ ] 1.2 Add unit coverage: a short marker-free page yields the bare-fallthrough
      shape; a short page with a wall marker yields the suspicious shape.

## 2. The complete-small-page promotion

- [ ] 2.1 Add `is_complete_small_page(observations, url) -> bool` in `actions/empty.py`,
      sharing `has_hard_wall_evidence` / `has_subresource_block_evidence` with
      `is_confirmed_empty`, differing only by dropping the `is_search_shaped` term
      and requiring a corroborating non-empty browser render.
- [ ] 2.2 Wire the promotion in `fetcher_response.py` (sibling to the empty
      promotion): on a positive conjunction, resolve verdict to `ok` so extraction
      runs on the real body; apply the confirmed confidence tier; apply the
      confirmed cache policy.
- [ ] 2.3 A thin page that is NOT corroborated-complete is unchanged: `content_thin`
      WARNING, body attached, `status: failed` + `retrieval_incomplete: true`.

## 3. Stop the wasted second render

- [ ] 3.1 In `playbook.py::_decide_gate_thin_escalate`, cap bare-fallthrough
      `length_floor` browser escalation at 1 (the corroborating witness); a
      wall-suspicious floor violation keeps the existing budget.

## 4. Tests + corpus + docs

- [ ] 4.1 Response test: a corroborated tiny complete page (fake HTTP + browser
      both returning the same ~230-char body, no wall) comes back `status: ok`
      with a populated `answer`, not `failed`.
- [ ] 4.2 Response test: a thin page WITH wall evidence stays `failed` +
      `content_thin` (the asymmetry holds — no false-positive promotion).
- [ ] 4.3 Corpus entry for `example.com` (stable structural fact: a tiny, complete,
      unwalled, non-search page must answer, not fail) so it is a regression guard,
      not a smoke-test footgun.
- [ ] 4.4 Update `LESSONS_LEARNED.md` #5 (the length_floor smoke-test footgun) to
      point at the promotion.
- [ ] 4.5 `make check` green; `make bench` if extraction/gate routing moved.
