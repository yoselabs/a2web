# cascade-decision-log Spec Delta — tighten-archive-rule-for-reddit

## MODIFIED Requirements

### Requirement: Escalation is decided by a pure planner over the observation log

The orchestrator's next action SHALL be chosen by a pure function `decide_next(log, url, caps) -> Action` that reads the entire observation log, the request URL, and the per-fetch caps. `decide_next` SHALL be total. The `Action` vocabulary SHALL include: `RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, and a `Continue` no-op action. `decide_next` SHALL be expressible as a decision table whose rows cover every combination of (most-recent observation kind and verdict, escalation evidence, per-fetch caps), each mapping to exactly one `Action`.

The URL-pattern rule that dispatches `RetryViaArchive` on a Reddit-comment URL when the most-recent observation is a tier `not_found` SHALL additionally require one of two pieces of "truly gone" evidence on the most-recent observation: (a) `authoritative == True` (the producing handler vouched the verdict is definitive for its domain), OR (b) `status_code == 404` (a hard HTTP 404). The rule SHALL also be vetoed when any observation in the log carries `subsystem == "js_required"` — that fingerprint identifies an anti-bot JS interstitial whose correct escalation is the browser tier, not archive.

#### Scenario: A soft-block observation yields EscalateBrowser with no winning tier

- **WHEN** the log holds only failure observations (no tier produced gate-passing content) and at least one carries a soft-block / JS-required signal, and the browser budget is unspent
- **THEN** `decide_next` returns `EscalateBrowser`

#### Scenario: Browser budget exhausted yields no further EscalateBrowser

- **WHEN** the caps show the browser dispatch budget is already spent
- **THEN** `decide_next` never returns `EscalateBrowser`

#### Scenario: Every condition combination maps to exactly one action

- **WHEN** the `decide_next` decision table is checked over the full product of its input conditions
- **THEN** every combination maps to exactly one `Action` — no missing row, no conflicting rows

#### Scenario: Handler-confirmed deleted Reddit comment escalates to archive

- **WHEN** the log's most-recent observation is a tier outcome with `verdict=not_found`, `authoritative=True`, and `source` is the Reddit site handler, on a Reddit-comment URL, with the archive budget unspent, and no observation in the log carries `subsystem="js_required"`
- **THEN** `decide_next` returns `RetryViaArchive(url=url)`

#### Scenario: Hard-404 Reddit comment escalates to archive

- **WHEN** the log's most-recent observation is a tier outcome with `verdict=not_found` and `status_code=404` on a Reddit-comment URL, with the archive budget unspent, and no observation in the log carries `subsystem="js_required"`
- **THEN** `decide_next` returns `RetryViaArchive(url=url)`

#### Scenario: JS-shielded Reddit comment does NOT short-circuit to archive

- **WHEN** the log's most-recent observation is a tier outcome with `verdict=not_found` on a Reddit-comment URL, but `authoritative=False`, `status_code != 404`, and some observation in the log carries `subsystem="js_required"`
- **THEN** `decide_next` does NOT return `RetryViaArchive` — it falls through to the next planner rule or `Continue`, leaving the JS-shielded page to the browser-escalation path (the existing `escalation.next_tier == "browser"` rule, or a subsequent planner round once the gate appends its observation)

#### Scenario: Reddit comment not_found without authoritative or 404 evidence does not retry archive

- **WHEN** the log's most-recent observation is a tier outcome with `verdict=not_found` on a Reddit-comment URL, `authoritative=False`, and `status_code != 404` (and no `js_required` is present either)
- **THEN** `decide_next` does NOT return `RetryViaArchive` — there is no evidence the content is truly gone
