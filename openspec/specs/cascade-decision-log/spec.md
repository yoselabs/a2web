# cascade-decision-log Specification

## Purpose

Fetch-cascade state is an append-only log of typed `Observation` records. The final verdict and every escalation decision are pure, total projections of that log — never a mutable scalar. This structurally eliminates the verdict-clobber bug class (last-write-wins on a single `final_verdict` slot) and concentrates all escalation policy in one pure planner.
## Requirements
### Requirement: Fetch state is an append-only observation log

One fetch SHALL accumulate its state as an append-only, immutable sequence of typed `Observation` records. Every tier attempt, quality-gate evaluation, and escalation SHALL append exactly one `Observation`; no component SHALL overwrite or mutate a prior `Observation`. An `Observation` SHALL carry at minimum: its `verdict`, its `source` (the tier / handler / gate that produced it), an `authoritative` flag (the source vouches the verdict is definitive for its domain), a relative timestamp, and structured evidence. The orchestrator SHALL NOT carry a mutable scalar `final_verdict` field — the verdict is derived, never stored.

#### Scenario: Each tier attempt appends one observation

- **WHEN** the cascade dispatches a tier and the tier returns a result
- **THEN** exactly one `Observation` is appended to the log carrying that tier's verdict and source

#### Scenario: A later observation never mutates an earlier one

- **WHEN** a downstream tier appends an observation after an upstream tier already appended one
- **THEN** the upstream observation is still present in the log, unchanged — no field of a prior observation is overwritten

#### Scenario: No mutable final-verdict slot exists

- **WHEN** static inspection walks `FetchContext`
- **THEN** there is no settable scalar `final_verdict` field — the final verdict is only obtainable by projecting the observation log

### Requirement: Final verdict is a pure total projection of the observation log

The final verdict SHALL be computed by a pure function `resolve_verdict(log) -> Verdict`, never stored. `resolve_verdict` SHALL be **total** — defined for every possible log, including the empty log — and SHALL select the verdict by an explicit precedence: any observation that is a successful gate-passing result yields `ok`; otherwise the highest-precedence failure verdict wins, where an `authoritative` observation outranks a non-authoritative one, and within each authority level a fixed `Verdict` ranking applies (definitive verdicts such as `not_found` / `paywall` / `anti_bot` outrank vague verdicts such as `length_floor` / `other`). `resolve_verdict` SHALL be **order-independent**: its result depends on the set of observations, not their arrival order.

#### Scenario: Authoritative not_found outranks a non-authoritative length_floor

- **WHEN** the log holds an authoritative `not_found` from a site handler and a non-authoritative `length_floor` from a generic tier, and no observation is gate-passing
- **THEN** `resolve_verdict` returns `not_found`

#### Scenario: A downstream gate-passing observation yields ok

- **WHEN** the log holds an earlier failure observation and a later observation that is a gate-passing success
- **THEN** `resolve_verdict` returns `ok` — a genuine recovery always wins

#### Scenario: The empty log yields a defined verdict

- **WHEN** `resolve_verdict` is called with an empty log
- **THEN** it returns a defined `Verdict` member, not an error or `None`

#### Scenario: Result is invariant under observation reordering

- **WHEN** `resolve_verdict` is called on a log and on any permutation of that log
- **THEN** both calls return the same `Verdict`

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

### Requirement: The fetch response derives its verdict from the observation log

`FetchResponse` SHALL be built by a pure function. Its `status`, `confidence`, `narrative`, and `diagnostics_summary` SHALL be derived from `resolve_verdict(observation log)` — no mutable verdict slot feeds them. The response SHALL be identical in shape and content to the response the prior orchestrator produced for the same fetch — this change introduces no wire / envelope change.

#### Scenario: Response verdict equals the resolved verdict

- **WHEN** a fetch completes and `FetchResponse` is built
- **THEN** the verdict reflected in `status` / `diagnostics_summary` equals `resolve_verdict(log)` for that fetch's observation log

### Requirement: Observations carry typed EscalationSignal values, not string suggested_tier fields

The `Observation` dataclass in `src/a2web/decision_log.py` SHALL replace its `suggested_tier: str | None = None` field with `escalation: EscalationSignal | None = None`. `EscalationSignal` is a frozen dataclass declared in `src/a2web/packages/escalation.py` (package-owned per the packages-independence rule, since `block_detector.py` — a package — produces it):

```python
NextTier = Literal["browser", "tls_impersonate", "archive"]

@dataclass(frozen=True, slots=True)
class EscalationSignal:
    next_tier: NextTier
    reason: str  # human-readable diagnostic, ≤80 chars
```

The planner (`actions/playbook.py::decide_next`) SHALL read `last.escalation` and switch on `last.escalation.next_tier` to choose an `EscalationBrowser` / `RetryViaArchive` / `RewriteUrl` action, rather than string-comparing `last.suggested_tier == "browser"`.

The signal is evidence-only; the planner remains the sole authority on whether to act (caps still gate execution). The signal carries the gate's / handler's recommendation, not a command.

#### Scenario: Gate emits EscalationSignal when JS-required is detected

- **WHEN** `block_detector.evaluate(...)` returns a `BlockResult` with `escalation=EscalationSignal(next_tier="browser", reason="js_required")`
- **THEN** the orchestrator appends a `gate_outcome` observation carrying that signal; the planner reads it via `last.escalation.next_tier == "browser"`

#### Scenario: Handler emits EscalationSignal for archive escalation

- **WHEN** a site handler (e.g. Reddit) encounters a 403 on a thread URL and decides archive is the right next step
- **THEN** the handler's `TierResult` carries an `escalation=EscalationSignal(next_tier="archive", reason="reddit_forbidden_try_archive")`; the orchestrator threads that into the tier observation; the planner sees the typed signal and dispatches `RetryViaArchive`

#### Scenario: No string-comparison on suggested_tier remains

- **WHEN** the codebase is grepped for `suggested_tier ==` or `suggested_tier !=`
- **THEN** zero matches exist; all decisions are made on typed `EscalationSignal.next_tier` Literal values

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

### Requirement: Transport and status failures escalate through the ladder

`decide_next` SHALL include `PlannerRule`s that route **ambiguous transport/status tier failures** into the escalation ladder by returning `EscalateBrowser`, so that no such failure ends the cascade without the browser (and, via the existing ladder, archive and paid) having been attempted. Each rule SHALL read the most-recent `tier_outcome` observation's `verdict`, `status_code`, and `authoritative` fields — the discriminator is the `status_code` already carried on the observation; the rules SHALL NOT require new `Verdict` members to be introduced in the tier layer.

The following tier-failure classes are **ambiguous** and SHALL escalate (each rule guarded by `browser_dispatches < 2` so it cannot re-fire past the browser cap):

- **403 forbidden** — `connection_error` with `status_code == 403`. Treated as anti-bot by default.
- **5xx server error** — `connection_error` with `status_code >= 500`.
- **other 4xx** — `connection_error` with `400 <= status_code < 500`, excluding 403 (and 404/429, which are their own verdicts).
- **timeout** — `Verdict.timeout`.
- **network/TLS drop** — `connection_error` with `status_code == 0` that is NOT a genuine DNS-resolution failure (see the DNS carve-out requirement).
- **uncorroborated 404** — `not_found` WITHOUT the `authoritative` flag.
- **exhausted 429** — `rate_limited` (retry/backoff already spent by the tier), generalized to every URL shape (not only search/listing).

These rules SHALL sit at `LOW` priority — below the `HIGH` gate-browser signal and the specific archive heuristics — so a more-specific content/gate-based decision always wins; they are the catch-all floor. They SHALL return `EscalateBrowser` (never `EscalatePaid` directly): the free self-hosted browser rung is tried first, and the existing `paid_last_resort` rule handles paid egress only after the browser cap is spent and the result is still a wall. `proxy_unavailable` (local proxy-pool exhaustion, not a site wall) SHALL NOT be swept into these rules.

Every added rule SHALL carry a unique `name` and a test pair, per the existing rule-identity contract.

#### Scenario: A 403 escalates to browser

- **WHEN** the last tier observation is `connection_error` with `status_code == 403` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: A 5xx escalates to browser

- **WHEN** the last tier observation is `connection_error` with `status_code == 502` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: A timeout escalates to browser

- **WHEN** the last tier observation is `Verdict.timeout` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: An uncorroborated 404 escalates to browser

- **WHEN** the last tier observation is `not_found` with `authoritative == False` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: An authoritative 404 does NOT escalate

- **WHEN** the last tier observation is `not_found` with `authoritative == True` (a site handler that models the site's real "gone" semantics)
- **THEN** the transport rules return `None` for this observation (the page is genuinely gone; no browser escalation)

#### Scenario: An exhausted 429 escalates on any shape

- **WHEN** the last tier observation is `rate_limited` (the tier already spent its retry/backoff) on a non-search, non-listing URL
- **THEN** `decide_next` returns `EscalateBrowser` (generalized from the prior search/listing-only render escalation)

#### Scenario: Transport rules do not fire past the browser cap

- **WHEN** any transport-failure observation is present but `browser_dispatches >= 2`
- **THEN** no transport rule returns `EscalateBrowser` (the ladder proceeds to paid / the loud terminal)

#### Scenario: A content-gate browser signal outranks the transport catch-all

- **WHEN** the log carries both a transport-failure observation and a `gate_outcome` with `escalation.next_tier == "browser"` (HIGH), with the browser budget unspent
- **THEN** the HIGH gate-browser rule's `EscalateBrowser` is what fires; the transport catch-all is not the deciding rule (same action, higher-priority source)

#### Scenario: proxy_unavailable is not swept into transport escalation

- **WHEN** the last tier observation is `proxy_unavailable` (local proxy-pool exhaustion, `status_code == 0`)
- **THEN** the transport rules return `None` (proxy exhaustion is not a site wall; it is handled at the proxy layer)

### Requirement: Genuine DNS resolution failure stays terminal, not escalated

A genuine DNS resolution failure (the domain does not resolve) SHALL be terminal — no browser, archive, or paid escalation — because a real browser resolves the same name identically; there is nothing to gain. This carve-out depends on the tier layer surfacing DNS failure as a distinct terminal `Verdict.dns_error` (adopted from the shelf `http-fetch` `FetchVerdict.dns_error`). The `network/TLS drop` transport rule (status-0 `connection_error`) SHALL fire only when the failure is NOT `dns_error`.

Until `dns_error` is available, the implementation MAY fall back to escalating all status-0 `connection_error` (a genuinely-dead domain then incurs one bounded, capped browser attempt before the loud terminal); this interim SHALL be tightened to the `dns_error` carve-out once the shelf verdict lands.

#### Scenario: NXDOMAIN does not escalate

- **WHEN** the last tier observation is `dns_error` (the domain does not resolve)
- **THEN** the transport rules return `None`; the cascade ends terminal (a real browser cannot resolve a nonexistent domain)

#### Scenario: A network drop that is not DNS still escalates

- **WHEN** the last tier observation is `connection_error` with `status_code == 0` that is NOT `dns_error` (connection reset / TLS handshake drop)
- **THEN** `decide_next` returns `EscalateBrowser` (a network-layer block may be passable by a real browser)


### Requirement: A blank_page verdict escalates through browser then paid before terminating

The `blank_page` verdict SHALL be a **wall-class** verdict for escalation: a cascade that ends on `blank_page` SHALL route through the escalation ladder — the self-hosted browser first, then the paid scraper rung — before any terminal is declared, exactly as content-gated wall verdicts (`block_page_detected`, `anti_bot`, `paywall`) do.

`Verdict.blank_page` SHALL be a total member of the verdict projection, ranked as a wall-class terminal (peer of `block_page_detected` / `anti_bot`) in the pure `_verdict_rank` projection, so the final verdict remains a pure total projection of the observation log.

The browser dispatch SHALL be driven by the gate's `EscalationSignal(next_tier="browser", reason="blank_page")` via the existing gate-browser rule. If the browser render re-gates to `blank_page`, the existing `paid_last_resort` rule SHALL carry the still-blank result to the paid scraper. Both dispatches SHALL respect the existing caps (browser ≤ 2, paid ≤ 1) so the ladder terminates; no new escalation action type is introduced.

#### Scenario: blank_page is ranked as a wall-class terminal

- **WHEN** `_verdict_rank` projects a log whose last outcome is `blank_page`
- **THEN** `blank_page` ranks as a wall-class terminal (a definitive miss, peer of `block_page_detected`), not as an `ok`/success

#### Scenario: A blank_page dispatches the browser via the gate signal

- **WHEN** the gate emits `blank_page` with `escalation.next_tier == "browser"` and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser` (the existing gate-browser rule fires on the typed signal)

#### Scenario: A blank_page surviving the browser reaches the paid scraper

- **WHEN** the browser render re-gates to `blank_page`, the browser cap is spent, and a paid tier is keyed with `paid_dispatches < 1`
- **THEN** `paid_last_resort` returns `EscalatePaid` (blank_page is a wall verdict the last-resort rung acts on)

#### Scenario: A blank_page past both caps stops escalating

- **WHEN** the log carries a `blank_page` outcome but `browser_dispatches >= 2` and `paid_dispatches >= 1`
- **THEN** no rule returns an escalation action (the ladder is exhausted; the loud terminal fires)
