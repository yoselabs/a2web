## 1. Neutral answer on selection questions (prompt)

- [x] 1.1 In `EXTRACT_ROUTER_V1.tail_template`, add the answer-neutrality rule for selection/decision questions over a set: no a2web-manufactured "best"; a criterion-disclosed lead only (name the criterion, frame as one lens); present the option space
- [x] 1.2 Add the relay-source-preference rule: when the page marks its own preference/featured/default, surface it attributed to the source ("the site marks X as preferred"), never as a2web's verdict
- [x] 1.3 Add the exhaustive-floor rule: neutral ≠ lazy — the answer presents the set + source preference + criteria in the same response, never declines-and-under-delivers
- [x] 1.4 Scope it: single-fact questions unchanged (the rule fires only for "which/best/compare/all over a set")
- [x] 1.5 Keep `cache_prefix_template` byte-identical (additions live in `tail_template`); verify the v0.19 cache-prefix invariant test still passes

## 2. Decouple criteria from partialness

- [x] 2.1 In `build_ask_response`, change the `refinement_axes` gate from `fr.items_loaded is not None` to the listing kind (`routing.structural_form == "listing"`)
- [x] 2.2 Broaden the prompt: ask for `refinement_axes` on any listing the user is selecting/comparing over (not only a truncated/sorted subset)
- [x] 2.3 Test: a complete listing selection surfaces `refinement_axes`; a non-listing omits them; empty axes still omit-empty

## 3. Product-invariant (ADR + CLAUDE.md, NOT CONSTITUTION.md per ADR-0009 precedent)

- [x] 3.1 Author `docs/adr/0012-shape-and-relay-never-manufacture-a-selection.md` and add the sibling line to CLAUDE.md's "Never" section (product tenet, not substrate governance)

## 4. Verification

- [x] 4.1 End-to-end: drive `ask` over a listing fixture; assert `refinement_axes` present on a complete listing (decoupled gate), and options/answer still coherent
- [x] 4.2 `make check` green (lint + ty + tests, coverage ≥85%); contract snapshot unchanged (no new fields)
- [x] 4.3 Update CHANGELOG.md
- [ ] 4.4 `make bench` after landing — the arbiter for the neutrality change; record findings in `eval/findings_<date>.md` (deferred, live network)
