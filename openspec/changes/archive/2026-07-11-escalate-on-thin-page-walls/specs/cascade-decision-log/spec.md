## ADDED Requirements

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
