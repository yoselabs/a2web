## ADDED Requirements

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

