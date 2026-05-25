# Tighten the Reddit-comment archive rule against JS-shielded pages

## Why

The 2026-05-25 bench run (`eval/runs/2026-05-25_183411/`) recorded a silent dead-end on `reddit-comments / a2web_extract`: the raw tier returned `verdict=not_found` carrying a `js_required` signal (Reddit served its anti-bot JS interstitial, not the comment thread). The same URL succeeded under `a2web_detail`, which escalated to the browser tier and returned content.

The planner rule at `src/a2web/actions/playbook.py:92-100` fired `RetryViaArchive` on the Reddit URL the moment it saw `verdict=not_found`. Archive has no live snapshot for the still-live page, so the fetch terminated with no content. This rule was correct when the only way a Reddit comment URL could produce `not_found` was a handler-confirmed deleted thread (the Reddit handler's `_archive_escalation_signal` path). After v0.22 `expand-js-shell-markers`, the raw tier produces the same closed `not_found` verdict on a JS-shielded page — two distinct failure modes are now collapsed onto one signal, and the URL-pattern rule no longer separates them.

The fix is narrowing the rule: archive is the right next step only when there is evidence the page is genuinely gone (authoritative handler-confirmed verdict, or a hard 404 status). When the observation log carries a `js_required` subsystem fingerprint, the rule must not fire — the gate's browser-escalation signal, or a later planner round, is the right path.

## What Changes

- **MODIFIED** the planner rule for `Reddit-comment URL + not_found → RetryViaArchive`: the rule now also requires the most-recent observation to be authoritative (handler-confirmed) OR to carry `status_code == 404`. When the most-recent observation has `subsystem == "js_required"` (or the log contains any prior `js_required` subsystem fingerprint), the rule does NOT fire and the planner falls through to its remaining rules / `Continue`.
- **MODIFIED** capability: `cascade-decision-log` — the `decide_next` requirement gains a scenario distinguishing "deleted Reddit comment" from "JS-shielded Reddit comment".
- No public API change. No wire / envelope change. No new dependencies.

## Impact

- Affected specs: `cascade-decision-log`.
- Affected code (implementation-only, not part of this proposal): `src/a2web/actions/playbook.py` (rule narrowing), `tests/capabilities/cascade_decision_log/test_decide_next.py` (two new branch scenarios).
- Affected operator behaviour: JS-shielded Reddit threads now reach the browser tier (the intended escalation) instead of silently dead-ending at archive. Genuinely deleted Reddit threads keep their existing archive-escalation path.
- Out of scope: generalising the discriminator to other handlers (HN, Discourse). That structural pattern will be handled in a separate proposal (`planner-rules-typed-priority`).
- Out of scope: changing the closed-enum semantics of `Verdict.not_found`.
