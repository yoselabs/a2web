## MODIFIED Requirements

### Requirement: Escalation is decided by a pure planner over the observation log

The orchestrator's next action SHALL be chosen by a pure function `decide_next(log, url, caps) -> Action` that reads the entire observation log, the request URL, and the per-fetch caps. `decide_next` SHALL be total. The `Action` vocabulary SHALL include: `RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, `EscalatePaid`, and a `Continue` no-op action.

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

#### Scenario: EscalatePaid is a member of the Action vocabulary the executor dispatches

- **WHEN** the `paid_last_resort` rule fires (a terminal wall after every free escalation is spent, paid budget unspent)
- **THEN** `decide_next` returns `EscalatePaid`, and the single executor dispatches it via the paid tier path

### Requirement: The orchestrator is a pure executor of planner actions

The orchestrator SHALL hold no escalation, rewrite, or stop policy of its own for planner-driven cascade escalation, and SHALL execute planner actions through **exactly one executor function**. That single executor SHALL handle the full `Action` union (`RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, `EscalatePaid`, `Continue`) in one place — no `Action` type is a silent no-op in a position where the planner can legally return it. There SHALL NOT be two divergent executors each handling a different subset of the `Action` union.

The single executor SHALL be invoked from both the tier-walk (after each tier appends its observation) and the post-gate escalation loop (after the gate appends its observation) — so the escalation ladder (`EscalateBrowser` → archive → `EscalatePaid`) is reachable from any position where an observation has just been appended, NOT gated behind the tier loop having produced a 2xx body to extract-and-gate. After appending an `Observation`, the orchestrator SHALL call `decide_next` and dispatch the returned `Action` through this one executor; every planner-driven escalation, rewrite, and cascade-stop decision SHALL originate from `decide_next`.

`RewriteUrl` — which restarts the tier walk — SHALL be modeled as a first-class control outcome of the single executor (a restart signal the tier loop consumes), so that the tier-loop-restart action and the escalation actions are dispatched by the same mechanism rather than by two phase-specific executors.

The one genuine pipeline-region divergence — `RetryViaArchive` installs the body only during the tier-walk (the gate runs later) but installs extracted fields and regates when dispatched post-gate — SHALL be an explicit parameter of the single executor, not a second executor. (Note: post-extraction completeness escalations — the obstacle-driven render, the listing scroll render, and the handler `escalate_to_render` ladder — are a separate concern folded into the planner in a follow-up change; this requirement governs the planner-driven cascade executor.)

#### Scenario: One executor handles every Action type

- **WHEN** the executor is exercised over representative log states that make `decide_next` return each of `RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, `EscalatePaid`, and `Continue`
- **THEN** the same single executor function dispatches each action correctly; no action type is a silent no-op in the position where the planner can legally return it

#### Scenario: Orchestrator escalates only on a planner action

- **WHEN** a tier result would historically have triggered an inline escalation but `decide_next` returns the continue / no-op action
- **THEN** the orchestrator performs no escalation and advances to the next pipeline step

#### Scenario: RewriteUrl restarts the tier walk via the single executor

- **WHEN** the planner returns `RewriteUrl` during the tier-walk (e.g. an arxiv PDF → abs-page rewrite) with the rewrite budget unspent
- **THEN** the single executor returns a restart control outcome, the tier loop restarts with the new URL, and the 1-rewrite cap is preserved

#### Scenario: The escalation ladder is reachable without a 2xx body

- **WHEN** the tier-walk appended a failure observation and the planner (now or via a future rule) returns an escalation action from that log
- **THEN** the single executor dispatches it — the ladder is not gated behind the tier loop having produced gate-passing content
