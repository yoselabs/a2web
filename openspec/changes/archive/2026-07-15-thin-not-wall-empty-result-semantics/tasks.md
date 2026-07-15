# Tasks — thin-not-wall-empty-result-semantics

## 1. Baseline

- [x] 1.1 Green baseline on affected suites: `tests/capabilities/retrieval_completeness/`, `tests/capabilities/ask_response/`, `tests/architecture/test_terminal_hint_coherence.py`, `tests/eval_replay/`.

## 2. `classify_terminal` — thin is corroboration-keyed (whole-log scan)

- [x] 2.1 `actions/terminal.py`: add `TerminalOutcome.thin_unverified`.
- [x] 2.2 Replace `_WALL_GATE_VERDICTS` (last-gate set incl. `length_floor`) with `_HARD_WALL_GATE_VERDICTS = {block_page_detected, anti_bot, paywall, blank_page}`, scanned across the WHOLE log via a new `_has_hard_wall_evidence(observations)` helper (any `gate_outcome` whose verdict is in the set).
- [x] 2.3 New precedence: paid_auth_error → unreachable → authoritative-gone → **hard-wall-anywhere → wall** → corroborated-404 → lone-404 → **last-gate==length_floor → thin_unverified** → default `wall` (bodyless transport + `other`).
- [x] 2.4 Docstring: record the whole-log-scan reason (the last-gate projection trap this module exists to prevent) and the `thin_unverified` semantics.

## 3. Hint + envelope

- [x] 3.1 `models.py`: add a `content_thin` hint constructor at `severity: warning`, capability-generic wording honest about what a2web did ("rendered in a headless browser and still under the length floor — most likely an empty result set or minimal page; content attached; small chance of an IP-keyed wall your own browser may differ on"). NEVER names a browser product beyond the generic escape hatch.
- [x] 3.2 `models.py`: add `AskResponse.thin_content: str | None = None`; wire it into the omit-empty serializer (absent unless populated; independent of `include_content`; wrapped per the untrusted-content rule).
- [x] 3.3 `fetcher.py` `_apply_terminal`: map `thin_unverified` → append `content_thin` hint (dedup like the others), set `retrieval_incomplete: true`, and stash the retrieved thin body on the context for the builder.
- [x] 3.4 `fetcher_response.py` `build_ask_response`: populate `thin_content` from the context ONLY on `thin_unverified`; leave it None otherwise. Confirm no LLM answer path runs on this outcome (already gated on success — assert, don't add).

## 4. Coherence table

- [x] 4.1 `tests/architecture/test_terminal_hint_coherence.py`: add the `thin_unverified: frozenset({"content_thin"})` row. The totality, mutual-exclusion (no outcome emits both `try_user_browser` and `content_not_found`), and only-`wall`-prescribes-browser invariants must still pass (`content_thin` is neither).

## 5. Unit + capability tests

- [x] 5.1 `test_classify_terminal.py`: (a) thin-200 clean log → `thin_unverified`; (b) `length_floor` last-gate WITH an early `anti_bot` gate obs → `wall` (whole-log scan); (c) totality still holds over the new member; (d) `thin_unverified` is the ONLY outcome carrying `content_thin`.
- [x] 5.2 `tests/capabilities/retrieval_completeness/`: a corroborated-thin 200 fetch → `status: failed`, `content_thin` warning, `thin_content` attached, NO `try_user_browser`; a thin-downstream-of-403 fetch → still `wall`/critical.
- [x] 5.3 `tests/capabilities/ask_response/`: `thin_content` present on `thin_unverified` without `include_content`; absent on `ok` and on `wall`.

## 6. Contract re-bless

- [x] 6.1 Re-bless `tests/contracts/tool_schemas.json` for the new `thin_content` field + `content_thin` hint code (`env A2WEB_BLESS_CONTRACTS=1`). Diff-review it is additive-only (new optional field, new hint code) — no removed/renamed fields.

## 7. Corpus

- [x] 7.1 `eval/corpus.yaml`: tighten `trendyol-200-soft-404-empty-results` criteria to assert (a) NO critical `try_user_browser`, (b) a `content_thin`/warning honest hedge, (c) the thin body is attached for the caller. Keep criteria phrased against stable structural facts.

## 8. Gate

- [x] 8.1 `make check` green (lint + ty + test, coverage ≥85%).
- [x] 8.2 `make arch` green (coherence + boundary invariants).
- [x] 8.3 Add the empty-result-as-`ok`-answer endgame to `BACKLOG.md` (deferred; needs a deterministic empty-vs-wall discriminator + caller-loop evidence).
- [ ] 8.4 (Deferred) `make bench` — live-network, LLM quota; tier terminal routing moved. Record findings in `eval/findings_<date>.md`.
