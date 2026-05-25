# Make planner rules a typed-priority table

## Why

`src/a2web/actions/playbook.py::decide_next` is the single escalation-policy function in the cascade. Today it is a flat if-chain of five rules where statement order silently encodes rule priority. Each rule's silent precondition (e.g. "no earlier rule already matched") lives only in the reviewer's head.

The 2026-05-25 bench run (`eval/runs/2026-05-25_183411/`) exposed how that brittleness fails. On a JS-shielded Reddit comment URL, the raw tier returned `Verdict.not_found` carrying a `js_required` subsystem fingerprint. Two rules were applicable:

- Rule 4 (Reddit-comment + `not_found` → `RetryViaArchive`).
- Rule 2 (gate signal `next_tier == "browser"` → `EscalateBrowser`) — but the gate observation arrives later and the planner only inspects `log[-1]`.

Rule 4 fired first because it sits earlier in the if-chain, the URL pattern matched, and the rule ignored the conflicting `js_required` signal already on the same observation. Archive had no snapshot, the fetch dead-ended with no content. The sibling proposal `tighten-archive-rule-for-reddit` patches Rule 4's precondition; this proposal removes the class of bug by making rule priority and preconditions explicit.

The rule set is also growing. Today: arxiv-rewrite, gate-browser, cloudflare-archive, reddit-archive, paywall-archive. Already shaped: cookie-handler escalation, paid-tier fallback, archive-on-handler-403. The if-chain does not scale — every new rule means picking a slot, re-reading every earlier rule's silent precondition, and hoping the next refactor does not shuffle the order.

A typed-priority planner makes each rule declare its preconditions and priority structurally. Adding a rule means appending one `PlannerRule` to a tuple; the enumerator finds the highest-priority applicable rule deterministically. Reviewers see one row per rule, not a control-flow graph.

## What Changes

- **ADDED** a `PlannerRule` frozen dataclass in `src/a2web/actions/playbook.py` carrying three fields: a `name: str` (identity + log key), a `priority: RulePriority` (closed enum: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`), and a `decide: Callable[[_RuleContext], Action | None]` (returns the action when applicable, `None` to defer). The planner enumerates a module-level `_RULES: tuple[PlannerRule, ...]` and returns the highest-priority non-`None` result; ties resolve by tuple order (declaration order is the tiebreaker).
- **MODIFIED** `decide_next` so its body is one enumeration loop; the five existing rules port one-for-one to `PlannerRule` instances. No public function signature changes.
- **MODIFIED** the `cascade-decision-log` capability: the existing `Escalation is decided by a pure planner` requirement gains language about rule enumeration and priority; an added requirement constrains rule-discipline (every new rule MUST add a positive + negative test pair).
- **PRESERVED** behaviour for four of the five existing rules. The fifth (Reddit-comment + `not_found`) now sits at `MEDIUM` priority while the gate-browser rule sits at `HIGH`, so a future log carrying both signals routes to browser, not archive. This is the same fix the sibling proposal `tighten-archive-rule-for-reddit` makes by narrowing Rule 4's precondition; if that sibling ships first, this proposal absorbs it cleanly (the rule lands at `MEDIUM` and its precondition stays narrowed). If this proposal ships first, the sibling is superseded — its narrowing is no longer needed because priority handles the conflict.
- **NOT CHANGED**: the `Action` ADT (`Continue` / `RewriteUrl` / `RetryViaArchive` / `EscalateBrowser`), `PlannerCaps`, `Observation`, or any wire / envelope. No new dependencies. The planner stays a pure, total function over `(log, url, caps)`.

## Impact

- Affected specs: `cascade-decision-log` (planner requirement).
- Affected code (implementation-only, not part of this proposal): `src/a2web/actions/playbook.py` (refactor), `tests/capabilities/cascade_decision_log/test_decide_next.py` (port + add the rule-discipline pair test).
- Affected operator behaviour: one bench-observable regression-fix. JS-shielded Reddit comment threads now escalate to browser (the intended path) instead of dead-ending at archive. Every other input produces the identical `Action` it produced before.
- Relationship to sibling `tighten-archive-rule-for-reddit`: that proposal is a precondition narrow on one rule; this proposal removes the class of bug. Both can ship; ordering does not matter. The one that ships second is a no-op delta — the merged tree converges on the same behaviour.
- Out of scope: a DSL or external rule engine, partial-order / topological priorities, splitting rules into per-file modules (deferred — single-file threshold documented in `design.md`).
