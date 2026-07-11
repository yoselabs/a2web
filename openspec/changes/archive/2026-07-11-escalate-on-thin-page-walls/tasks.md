## 1. Grounding + verdict plumbing

- [x] 1.1 Confirm the exact `block_detector.evaluate` control flow and the bare `length_floor` fallthrough (`block_detector.py:237-238`); confirm `raw_html` is available to the branch and is the unextracted body.
- [x] 1.2 Add `BlockVerdict.blank_page` (package `block_detector.py`) and `Verdict.blank_page` (domain `models.py`). Keep the `BlockVerdict(...).value → Verdict(...)` seam mapping intact.
- [x] 1.3 Rank `blank_page` in `decision_log._verdict_rank` as a wall-class terminal (peer of `block_page_detected` / `anti_bot`); keep the `match` exhaustive with `assert_never`.

## 2. Gate detection

- [x] 2.1 Add a `BLANK_HTML_THRESHOLD` constant + a visible-text helper (strip tags + collapse whitespace on `raw_html`). Tune the threshold so `<html></html>` / empty shells match but a ~480-char visible-text stub does not.
- [x] 2.2 Insert the `blank_page` branch in `evaluate` AFTER all marker branches and the `js_required` JS-shell branch, and BEFORE the bare `length_floor` fallthrough. Return `BlockResult(BlockVerdict.blank_page, escalation=EscalationSignal(next_tier="browser", reason="blank_page"))`.
- [x] 2.3 Confirm the extracted-thin `length_floor` path (substantial raw HTML, thin `content_md`) is untouched — the two populations must stay disjoint.

## 3. Escalation ladder + terminal

- [x] 3.1 Add `blank_page` to `fetcher._WALL_VERDICTS` so `paid_last_resort` + the loud-terminal path run for it. Verify the gate-browser rule dispatches the browser on the `blank_page` escalation signal, and that browser→paid ordering + caps (browser ≤ 2, paid ≤ 1) hold (no spin).
- [x] 3.2 Emit a distinct `blank_page` operator hint (new `OperatorHint` code, honest message naming the empty-source outcome) when a `blank_page` survives the ladder — NOT `try_user_browser`. Ensure `_has_browser_hint` dedup does not suppress it and that `try_user_browser` is NOT also emitted for this verdict.
- [x] 3.3 Confirm the surviving-`blank_page` terminal sets `status: failed` + `retrieval_incomplete: true` on the wire (extend the retrieval_incomplete derivation if needed, mirroring the transport-wall hook).

## 4. Tests

- [x] 4.1 Gate unit tests: empty `<html></html>` → `blank_page` + browser escalation; ~480-char visible-text stub → NOT `blank_page` (stays `length_floor`); substantial-HTML/thin-`content_md` → `length_floor` unchanged; fingerprinted empty shell → keeps its specific marker verdict (js_required / anti_bot), not `blank_page`.
- [x] 4.2 Planner unit tests: `blank_page` → `EscalateBrowser` via the gate signal; a re-gated `blank_page` with browser spent + paid keyed → `EscalatePaid`; past both caps → no escalation.
- [x] 4.3 End-to-end `fetch()` test: a raw tier returning a near-empty body escalates to a (stub) browser; a browser that recovers real content ends `ok`; a browser + paid that both return blank ends `status: failed` + `retrieval_incomplete` + the distinct `blank_page` hint (and NOT `try_user_browser`).
- [x] 4.4 Verify verdict projection stays pure/total with `blank_page` added; update any existing test that fed a near-empty raw body expecting bare `length_floor` (legitimate expectation change).

## 5. Verification

- [x] 5.1 Run `make check` (lint + ty + full test + coverage ≥85%) and `make arch`.
- [x] 5.2 Re-bless the contract snapshot (`A2WEB_BLESS_CONTRACTS=1 uv run pytest tests/contracts/test_contracts.py::test_contract_tool_schemas`) to capture the new `blank_page` verdict enum value + hint code. Confirm the diff is ONLY the additive blank_page changes (watch for pre-existing WIP entanglement).
- [x] 5.3 Update `block_detector` / `playbook` docstrings + the `quality-gate` rule-catalogue comment to describe the blank_page branch and its raw-HTML (not extracted) keying.
- [x] 5.4 Live sanity: fetched a spread of real hosts.
  - VERIFIED 2026-07-11 on `g2.com`: full chain fired live — `raw 403 → archive(200) → gate=blank_page → browser(timeout) → browser_robust(length_floor)` → `status=failed` + `retrieval_incomplete=true` + `hints=['blank_page']` (the distinct honest hint, NOT `try_user_browser`). The gate flagged blank_page on a near-empty archive body and escalated through both browser rungs before the loud terminal — exactly as designed.
  - Also observed live: `nseindia.com` recovered via `browser_robust`; SPAs (telegram/excalidraw/linear/vercel) correctly stayed `length_floor`/`ok` (their shells carry >32 visible chars — blank pages are genuinely rare, as expected). `zillow.com` reproduced the pre-existing content-wall-with-body `try_user_browser` gap (separate follow-up, not this change).
