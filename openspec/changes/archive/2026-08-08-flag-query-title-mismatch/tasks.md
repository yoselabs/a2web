## 1. Ask-First sign-off

- [x] 1.1 Confirm the confidence-cap/hint behavior change with the user before writing any implementation code, per `AGENTS.md` Ask First — same gate `a2web-7bj.12` and `type-listing-commerce-fields` got.

## 2. Token-overlap helper

- [x] 2.1 Add a small, fixed, English-only operator-word constant near `served_url_differs` in `fetcher_response.py` (or a nearby module), drafted against the audit's quoted queries and `routers.py`'s tool-description examples — not a general English stopword list.
- [x] 2.2 Add a pure normalize/tokenize helper: casefold, Unicode NFKD + strip combining marks, split on non-alphanumeric, drop tokens under 3 chars.
- [x] 2.3 Add a pure `_query_title_mismatch` (or similar) helper: strip operator words from the query's tokens; if empty, return "no signal"; else return whether ANY served item title (from a list of strings) shares a normalized token with the remaining query tokens.
- [x] 2.4 Unit tests for the helper: stopword stripping leaves nothing → no signal; NFKD normalization handles a Turkish/Cyrillic example; any-one-item-overlaps → no mismatch; zero-overlap across all items → mismatch.

## 3. Wire into `build_response`

- [x] 3.1 Add `query_title_mismatch_hint()` to `hints.py`, mirroring `served_url_differs_hint`'s docstring/shape (`warning` severity, names the query and a sample of served titles).
- [x] 3.2 In `build_response` (`fetcher_response.py`), after the existing `served_url_differs` block, gate on `fc.inputs.ask` non-empty, `fc.routing` classified `listing` (decide against the existing `is_listing` gate used for `options` — see design.md Open Questions), and `fc.record_set` non-empty. Feed `[r.heading_text for r in fc.record_set.records if r.heading_text]` into the helper.
- [x] 3.3 Apply the same downgrade-only cap variable the `served_url_differs` block uses — confirm the cap doesn't double-apply beyond `medium` when both checks fire (per spec's last scenario).
- [x] 3.4 Confirm `ResponseContext` Protocol already exposes everything needed (`inputs.ask`, `routing`, `record_set` — all pre-existing members, no slice-budget change expected this time).

## 4. Tests and verification

- [x] 4.1 New test file mirroring `tests/capabilities/retrieval_completeness/test_served_url_identity_mismatch.py`'s shape: zero-overlap flags, any-overlap doesn't, non-listing doesn't, empty-after-stopword-strip doesn't, cap is downgrade-only and doesn't double-apply with `served_url_differs`.
- [x] 4.2 Run `make check` (lint + ty + test, coverage ≥85%).
- [x] 4.3 Mutation-verify: mutate the new check, confirm the relevant test(s) go red for the right reason, restore, re-verify green.
- [x] 4.4 Run `uv run pytest tests/contracts/ -q`; re-bless via `make bless-wire SLUG=<reason>` only if a golden fixture's confidence/hints actually change (unexpected — no existing fixture is a zero-overlap listing). — N/A: 36/36 passed unchanged.
- [x] 4.5 Run `make recon-check`.

## 5. Docs and close-out

- [x] 5.1 Sync `openspec/specs/fetch-response/spec.md` with the delta in this change.
- [x] 5.2 Close `a2web-byy` with a reason summarizing what shipped vs. deferred (confusable-model-variant shape on single product pages stays open — own bead if pursued, per design.md Non-Goals).
- [ ] 5.3 Archive this change once merged.
