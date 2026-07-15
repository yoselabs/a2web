# Tasks — empty-vs-wall-discrimination

Staged A→D. Run `make check` + `make arch` green between stages; each stage is
independently shippable (D is the only breaking flip).

## 0. Baseline

- [x] 0.1 Green baseline on affected suites: `tests/capabilities/retrieval_completeness/`, `tests/capabilities/quality_gate/`, `tests/capabilities/tier_pipeline/`, `tests/capabilities/ask_response/`, `tests/architecture/test_terminal_hint_coherence.py`.

## A. Honest wording (non-breaking)

- [x] A.1 `models.py::content_thin_hint`: drop the "most likely an empty result set" base-rate assertion; reword symmetric/agnostic ("thin — could be an empty result OR a wall we couldn't fingerprint; body attached, you judge"). Keep body-attached + residual-wall disclosure + browser escape hatch, `severity: warning`.
- [x] A.2 `actions/terminal.py`: reword the `thin_unverified` docstring (line ~41) to match — no base-rate claim.
- [x] A.3 Update any test asserting the old wording; re-bless nothing (message text is not contract).

## B. Extend the WALL catalogue (non-breaking)

- [x] B.1 `packages/block_detector.py::_BLOCK_PATTERNS`: add bounded bespoke-wall phrases — PerimeterX "pardon the interruption", generic "access denied", "request unsuccessful" (Incapsula/Imperva). High-precision, IGNORECASE.
- [x] B.2 `tests/capabilities/quality_gate/`: a sub-floor PerimeterX body → `block_page_detected` (hard wall), not bare `length_floor`.

## C. Subresource-block evidence (non-breaking, new observation)

- [x] C.1 `packages/browser_backends/base.py`: add `RenderedPage.subresource_blocks: int = 0` (domain-free int).
- [x] C.2 `packages/browser_backends/playwright.py::render`: attach `page.on("response", …)` before `goto`, counting responses with `request.resource_type in {"xhr","fetch"}` and `status in {401,403,429}`; best-effort (never raises); surface on the returned `RenderedPage`. Detach the listener on exit.
- [x] C.3 `tiers/__init__.py` (`TierResult`): add `subresource_blocks: int = 0` (typed field — no `tier_extras`).
- [x] C.4 `tiers/browser.py`: copy `page.subresource_blocks` onto the returned `TierResult`.
- [x] C.5 `decision_log.py` (`Observation`): add `subresource_blocks: int = 0` beside `status_code`/`cloudflare`.
- [x] C.6 `fetcher.py`: when appending the browser `tier_outcome` observation, copy `subresource_blocks` from the browser `TierResult`.
- [x] C.7 `packages/block_detector.py`: add `_EMPTY_RESULT_PATTERNS` + the empty-marker annotation branch (sub-floor, no wall/JS-shell/blank fingerprint, empty phrase matched → `length_floor` with `subsystem="empty_result"`, no escalation). Runs AFTER every wall/JS-shell/blank branch.
- [x] C.8 `actions/terminal.py`: add `TerminalOutcome.empty_unverified`. New precedence: paid_auth_error → unreachable → authoritative-gone → **subresource-block-anywhere → wall** → hard-wall-anywhere → corroborated-404 → lone-404 → **last-gate length_floor + subsystem==empty_result → empty_unverified** → last-gate length_floor → thin_unverified → wall. Add `_has_subresource_block_evidence(observations)` (any obs with `subresource_blocks > 0`).
- [x] C.9 `fetcher.py::_apply_terminal`: map `empty_unverified` → `content_thin` hint (may lean empty) + `retrieval_incomplete: true` + attach body (reuse the `thin_unverified` path).
- [x] C.10 `tests/architecture/test_terminal_hint_coherence.py`: add the `empty_unverified: frozenset({"content_thin"})` row; totality + only-`wall`-prescribes-browser invariants hold.
- [x] C.11 Unit tests (`test_classify_terminal.py`): subresource-block-anywhere → `wall` (even with empty marker); empty-marker + weak corroboration → `empty_unverified`; totality over the new member.
- [x] C.12 Backend unit test: a fake/stubbed response stream with a 403 XHR → `subresource_blocks >= 1` on `RenderedPage` (no live browser — exercise the listener/count helper directly).

## D. Corroborated empty → ok (BREAKING: failed→ok flip — Ask First, authorized)

- [x] D.1 `domain.py`: add `is_search_shaped(url) -> bool` (query param present, or a `/search|/arama|/sr|/s|/results` path segment). Pure.
- [x] D.2 New `actions/empty.py`: `is_confirmed_empty(observations, url) -> bool` — the full conjunction (browser regate-empty corroboration AND a body-returning HTTP tier AND no 4xx/challenge status anywhere AND no subresource-block evidence AND no hard-wall evidence AND `is_search_shaped`). Pure, total, no I/O. Reuse public `has_hard_wall_evidence` / `has_subresource_block_evidence`. NOTE (implementation-revealed): corroboration is by the browser, not jina — a thin 200 wins the tier loop so jina never runs on it; the browser escalation is the second independent retrieval.
- [x] D.3 `models.py`: add `content_empty_hint(url)` at `severity: info`; add `AskResponse.thin_content` population on the promoted-ok path (extend the existing field, already added in thin-not-wall).
- [x] D.4 `fetcher.py`: after `resolve_verdict`, if verdict != ok and `is_confirmed_empty(log, url)` → promote: build an `ok` response with a synthetic "no results" answer (confidence low), `content_empty` info hint, body attached, `retrieval_incomplete` false, and mark the response NO-CACHE. Only then, else, fall to `classify_terminal`.
- [x] D.5 `fetcher_response.py`: synthetic empty `answer` builder (never fabricates items); ensure the promoted empty is excluded from cache-write (alongside the block-page guard).
- [x] D.6 `cache.py` / cache-write phase: assert a promoted-empty response never enters cache (test the invariant).
- [x] D.7 Capability tests (`tests/capabilities/retrieval_completeness/`): corroborated empty (raw+jina thin, empty marker, search URL, clean) → `ok` + synthetic answer + `content_empty` + body + not cached; a 403-anywhere → `wall`; a non-search URL → `empty_unverified`; jina-missing → `empty_unverified`.
- [x] D.8 `tests/capabilities/ask_response/`: promoted-empty answer shape (low confidence, no fabricated items, `thin_content` present).

## E. Contract + corpus + gate

- [x] E.1 Re-bless `tests/contracts/tool_schemas.json` (`env A2WEB_BLESS_CONTRACTS=1`). Diff-review: the new `content_empty` hint code is additive; the `ok`-empty is a status-value change on an existing field, NOT a shape change — confirm no field removed/renamed.
- [x] E.2 `eval/corpus.yaml` (same session, repo rule): add (a) a bespoke-wall thin 200 (PerimeterX "pardon the interruption") asserting `wall`/critical; (b) a genuine TR 0-result storefront search asserting promoted-`ok`/`content_empty`/no-critical; (c) if a live SPA-walled-API fake-empty is found, one asserting `wall` (subresource evidence). Criteria phrased structurally.
- [x] E.3 `make check` green (lint + ty + test, coverage ≥85%).
- [x] E.4 `make arch` green (coherence + boundary + `tier_extras` + packages-independence invariants).
- [ ] E.5 (Deferred) `make bench` — live-network, LLM quota; empty/wall routing moved. Record findings in `eval/findings_<date>.md`. Confirm with user before running (subscription-only, ADR-0016).
