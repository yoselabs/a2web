# cascade-decision-log Spec Delta — planner-rules-typed-priority

## MODIFIED Requirements

### Requirement: Escalation is decided by a pure planner over the observation log

The orchestrator's next action SHALL be chosen by a pure function `decide_next(log, url, caps) -> Action` that reads the entire observation log, the request URL, and the per-fetch caps. `decide_next` SHALL be total. The `Action` vocabulary SHALL include: `RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, and a `Continue` no-op action.

`decide_next` SHALL be implemented as the enumeration of a module-level immutable tuple of `PlannerRule` instances. Each `PlannerRule` SHALL declare three fields explicitly: (a) a `name: str` identifying the rule, (b) a `priority: RulePriority` drawn from a closed enum with at least four levels (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), and (c) a pure callable returning `Action | None` over the planner's input context (the observation log, the most-recent observation, the URL, and the caps). A rule that returns `None` SHALL defer to the next rule.

`decide_next` SHALL evaluate every rule whose priority can still produce a winning action, pick the highest-priority rule whose callable returned a non-`None` action, and return that action. Within a single priority level, declaration order in the rules tuple SHALL be the tiebreaker. When no rule yields an action, `decide_next` SHALL return `Continue()`.

`decide_next` SHALL remain a pure, total, deterministic function — no rule callable performs I/O, captures mutable state, reads globals, or depends on wall-clock time.

#### Scenario: A soft-block observation yields EscalateBrowser with no winning tier

- **WHEN** the log holds only failure observations (no tier produced gate-passing content) and at least one carries a soft-block / JS-required signal, and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: Browser budget exhausted yields no further EscalateBrowser

- **WHEN** the caps show the browser dispatch budget is already spent
- **THEN** `decide_next` never returns `EscalateBrowser`

#### Scenario: Every condition combination maps to exactly one action

- **WHEN** the `decide_next` decision table is checked over the full product of its input conditions
- **THEN** every combination maps to exactly one `Action` — no missing row, no conflicting rows

#### Scenario: Higher-priority rule outranks lower-priority rule on the same log

- **WHEN** the log carries evidence that triggers both a `HIGH`-priority rule and a `MEDIUM`-priority rule on the same call to `decide_next`
- **THEN** `decide_next` returns the `HIGH`-priority rule's action; the `MEDIUM`-priority rule does not fire

#### Scenario: Declaration order resolves ties within a priority level

- **WHEN** two rules at identical priority both return non-`None` actions for the same `(log, url, caps)`
- **THEN** the rule declared earlier in the rules tuple wins; the result is deterministic across runs

#### Scenario: Gate-browser signal outranks Reddit-comment archive rule

- **WHEN** the log carries (a) a tier observation on a Reddit-comment URL with `verdict=not_found` carrying `subsystem="js_required"`, and (b) a later gate observation with `escalation.next_tier="browser"`, with the browser budget unspent
- **THEN** `decide_next` returns `EscalateBrowser` (the gate-browser rule at `HIGH`), not `RetryViaArchive` (the Reddit-comment rule at `MEDIUM`)

## ADDED Requirements

### Requirement: Every planner rule has an identity and a test pair

Every `PlannerRule` registered in the planner's rules tuple SHALL have a stable string `name` that uniquely identifies the rule across the codebase. The rule's `name` SHALL appear in at least two test functions: one asserting the rule fires when its precondition holds (positive case), and one asserting the rule does not fire when its precondition fails or a higher-priority rule wins (negative case). The convention for the test names SHALL be `test_<rule_name>_fires_when_<condition>` and `test_<rule_name>_does_not_fire_when_<condition>`.

This discipline is enforced by code review, not by a runtime guard — the spec captures the convention so reviewers reject rule additions that lack the test pair.

#### Scenario: A new rule arrives with positive + negative tests

- **WHEN** a contributor adds a new `PlannerRule` to the rules tuple
- **THEN** the same patch adds at least one `test_<rule_name>_fires_when_*` and at least one `test_<rule_name>_does_not_fire_when_*` test; reviewers reject the patch otherwise

#### Scenario: Rule names are unique

- **WHEN** the rules tuple is enumerated
- **THEN** every rule's `name` field is distinct from every other rule's `name`

### Requirement: Planner rules live in a single file until the documented threshold

All `PlannerRule` instances SHALL be declared in `src/a2web/actions/playbook.py` (or its successor single-file location) for as long as the rules tuple holds 10 or fewer rules. When the tuple reaches 11 rules, the rules SHALL be split into per-category modules under `src/a2web/actions/playbook/rules/` (one module per priority level), and the planner module re-imports them in a single tuple. This threshold is structural, not advisory — it removes the per-PR "should we split?" debate.

#### Scenario: Rules tuple has 10 or fewer rules

- **WHEN** `_RULES` holds ≤ 10 entries
- **THEN** every `PlannerRule` instance is declared in the single planner module file

#### Scenario: Rules tuple crosses the threshold

- **WHEN** the rules tuple would grow past 10 entries
- **THEN** the rules MUST be split into per-category modules before the new rule lands; the patch that adds the 11th rule also performs the split
