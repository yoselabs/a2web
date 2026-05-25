# Design — planner-rules-typed-priority

## Context

`decide_next` is a 50-line pure function in `src/a2web/actions/playbook.py`. The orchestrator calls it after each tier and after the gate; the returned `Action` is executed verbatim. The function is the single concentration point for all escalation policy (per the `cascade-decision-log` capability's pure-planner requirement).

Today five rules live in a flat if-chain. Statement order = priority. The bug captured in `proposal.md` is the structural consequence: applicable-but-lower-priority rules silently win over higher-priority rules whose observations arrived later.

This design picks the lightest typing that makes (a) preconditions explicit per rule, (b) priority declared not implied, and (c) rule discipline (test pair per rule) enforceable. We deliberately avoid a DSL, a rule engine, or a partial-order resolver.

## Decisions

### Decision 1 — priority representation: closed enum, four levels

**Chosen.** `class RulePriority(IntEnum): CRITICAL = 4; HIGH = 3; MEDIUM = 2; LOW = 1`.

**Alternatives considered:**

- _Flat int 1–100_. Rejected. Two-digit priorities (`72`, `55`) carry no semantics; reviewers cannot compare without going back to the table. Encourages priority creep ("just bump this to 73"). The current rule set has natural buckets, not a smooth gradient.
- _Partial order / topological sort over `dominates` edges_. Rejected. Heaviest by far; needs a cycle detector, a sort, an opaque resolution algorithm. Five rules do not justify it. Revisit when we have >15 rules or a real partial-ordering case (we have none today).

**Rationale for the enum.** Four levels covers the rule set with room to grow:

- `CRITICAL` — URL normalisation that must run before any tier-vs-gate logic considers the URL (arxiv PDF rewrite is the only current example; it fires regardless of the log).
- `HIGH` — explicit typed escalation hints from gate / handler (`EscalationSignal.next_tier == "browser"` today; cookie-handler hint and paid-tier hint when added).
- `MEDIUM` — URL-pattern + verdict combinations where the planner inferred (not was told) the right escalation (Reddit-comment + `not_found` → archive; HN-deleted → archive when added).
- `LOW` — failure-class escalations of last resort (Cloudflare-403 → archive; gate paywall → archive; gate block-page → archive).

Tiebreaker within a level is declaration order in `_RULES`. This makes "two rules at the same priority fired in this order" reviewable from a single file location.

### Decision 2 — where rules live: one file, threshold at 10

**Chosen.** All `PlannerRule` instances stay in `src/a2web/actions/playbook.py` as a module-level `_RULES: tuple[PlannerRule, ...]`. One file, one tuple, scrollable in a single screen for ≤10 rules.

**Threshold.** When `_RULES` reaches 10 entries, split into `actions/playbook/rules/<category>.py` (one module per priority level). The split is mechanical and reversible; documenting the threshold up front prevents the "should I split now?" debate on every new rule.

**Rationale.** Five rules fit on one screen today. A directory of one-rule files would obscure the priority table — the readability win lives in seeing all rules in one place. The threshold is a structural trigger, not a judgement call.

### Decision 3 — precondition typing: a Callable over a typed context object

**Chosen.** Each `PlannerRule.decide` is a `Callable[[_RuleContext], Action | None]` where `_RuleContext` is a frozen dataclass bundling everything a rule can read:

```python
@dataclass(slots=True, frozen=True)
class _RuleContext:
    log: Sequence[Observation]
    last: Observation | None        # log[-1], pre-computed
    url: str
    caps: PlannerCaps
```

The rule returns the action when it applies, `None` to defer to the next rule. Rules are plain functions named `_rule_<name>` declared above the `_RULES` tuple.

**Alternatives considered:**

- _Pydantic-like `RulePredicate` ADT_ (`AndPredicate`, `OrPredicate`, `KindIs`, `VerdictIn`, …). Rejected. Heavyweight. The predicates in the existing five rules are not reusable across rules — each rule's match is a sui-generis combination of fields. An ADT would multiply types without removing branching.
- _Stringly-typed precondition strings parsed at startup_. Rejected. A DSL the team will neither lint nor refactor.
- _Two callables per rule (`predicate` + `action_builder`)_. Rejected. The split is artificial: the rule must read the same `_RuleContext` twice, and a buggy rule can have its predicate return True while the builder cannot construct a valid action (e.g. arxiv regex group missing). One callable returning `Action | None` is one branch, atomic.

**Rationale.** The callable-with-context shape is Pythonic, type-checked end-to-end (mypy / ty see `Action | None`), and reads like the existing if-chain — each rule body is the same few lines as today, just lifted into a named function. The context object means a rule's input surface is documented by its signature, not by reading the planner.

### Decision 4 — purity is non-negotiable

**Chosen.** The planner stays a pure, total function over `(log, url, caps)`. Rule functions:

- MUST NOT perform I/O.
- MUST NOT capture mutable state.
- MUST NOT read environment / settings / globals.
- MUST be deterministic — same `_RuleContext` always yields the same `Action | None`.

The existing `cascade-decision-log` pure-planner requirement carries forward unchanged; the rule-table refactor is an internal restructuring.

### Decision 5 — rule discipline: positive + negative test pair per rule

**Chosen.** Every `PlannerRule` MUST have at least one test that asserts "fires when" and at least one that asserts "does not fire when". The test names follow `test_<rule_name>_fires_when_<condition>` and `test_<rule_name>_does_not_fire_when_<condition>`.

This is enforceable as a soft convention (added to the spec as a requirement, not as a runtime guard). Two practical effects:

- New-rule reviewers see the test pair in the diff or reject the PR.
- The negative test forces the author to articulate the precondition explicitly — exactly the discipline the old if-chain lacked.

We deliberately do not add a meta-test that walks `_RULES` and greps for `test_<name>_fires_when` / `test_<name>_does_not_fire_when` — that machinery would be more complex than the discipline it enforces, and it would break under legitimate test renames. Code review is sufficient.

### Decision 6 — relationship with `tighten-archive-rule-for-reddit`

The sibling proposal is a precondition narrow on one rule. This proposal is a structural refactor. The two are independent:

- If `tighten-archive-rule-for-reddit` ships first: that proposal's narrowed precondition is preserved here as the Reddit rule's `decide` body. Priority levels still help — the narrowed rule lands at `MEDIUM`, the gate-browser rule at `HIGH`, the bug stays fixed structurally.
- If this proposal ships first: the priority ordering alone fixes the bug (gate-browser at `HIGH` outranks Reddit-archive at `MEDIUM`). The sibling becomes a no-op delta — its narrowing is no longer required for correctness, though it remains harmless and slightly tightens the rule.
- If both ship: belt + suspenders. No conflict.

Neither proposal blocks the other. They are recorded as related-not-dependent in their respective `proposal.md`.

## Open questions

None. The shape is small enough that all five rules port mechanically; the only judgement call is the per-rule priority assignment, which is captured in `tasks.md`.
