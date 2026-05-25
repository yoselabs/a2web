# Tasks — tighten-archive-rule-for-reddit

## 1. Confirm the signal shape

- [x] 1.1 Read `src/a2web/decision_log.py` and confirm `Observation` carries the four fields the rule reads: `verdict`, `authoritative`, `status_code`, `subsystem`. Confirm `subsystem` is the place `js_required` lands (per `src/a2web/packages/block_detector.py`).
- [x] 1.2 Read `src/a2web/handlers/reddit.py::_archive_escalation_signal` and confirm it returns a `TierResult` that the orchestrator threads into an observation with `authoritative=True` and `status_code=0` (handler-shape projection). Note: if `authoritative` is not currently set on that path, raise a question before implementation — the narrowing depends on it.
- [x] 1.3 Grep `src/a2web/` for other producers of `subsystem="js_required"` to confirm the veto's blast radius. Document any non-Reddit producer in a code comment if surprising.

## 2. Narrow the planner rule

- [x] 2.1 In `src/a2web/actions/playbook.py`, modify the existing Reddit-comment rule (lines 92-100 as of writing) to add two conditions:
  - the most-recent observation must satisfy `last.authoritative or last.status_code == 404`,
  - no observation in the log may carry `subsystem == "js_required"`.
- [x] 2.2 Update the inline comment block above the rule to explain the two-signal "truly gone" discriminator and the `js_required` veto, and to point readers at the design doc for the deferred structural fix (`planner-rules-typed-priority`).
- [x] 2.3 Run `make lint && make ty` to confirm no static-analysis fallout.

## 3. Add tests + verify

- [x] 3.1 In `tests/capabilities/cascade_decision_log/test_decide_next.py`, add four targeted scenarios:
  - `test_reddit_comment_authoritative_not_found_retries_via_archive` — handler-confirmed, no js_required veto, expects `RetryViaArchive`.
  - `test_reddit_comment_404_retries_via_archive` — hard 404, no js_required veto, expects `RetryViaArchive`.
  - `test_reddit_comment_js_required_does_not_retry_archive` — `subsystem="js_required"` somewhere in the log; even with `not_found` on a comment URL, the rule must NOT fire (`Continue` or whatever the next rule returns).
  - `test_reddit_comment_not_found_without_evidence_does_not_retry_archive` — `authoritative=False`, `status_code != 404`, no js_required; expects no archive dispatch.
- [x] 3.2 Extend the `_tier` test helper (or add a sibling) so callers can pass `subsystem` for the veto test. Keep existing helper signatures backwards-compatible.
- [x] 3.3 Audit the rest of `decide_next` to confirm no other rule subsumes the Reddit-comment-not-found case (grep for `_REDDIT_COMMENT_RE` and `not_found`). If a generic rule would fire instead, surface that in the design doc as a follow-up question.
- [x] 3.4 Run `make test` and confirm all `test_decide_next.py` cases pass, including the existing `test_reddit_comment_not_found_retries_via_archive` (which already happens to satisfy the new narrowing — it sets `authoritative=True`).
- [x] 3.5 Run `make check` — coverage gate (≥85%) must still hold.
