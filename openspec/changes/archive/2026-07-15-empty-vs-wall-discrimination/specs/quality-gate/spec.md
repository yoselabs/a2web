## ADDED Requirements

### Requirement: Empty-result marker annotates a thin length_floor

The content gate SHALL recognize a conservative, high-precision set of empty-result phrases (`_EMPTY_RESULT_PATTERNS` — multilingual, e.g. "no results", "0 products", "did not match", "aradığınız … bulunamadı", "sonuç bulunamadı") on a sub-floor body. When a body is below `LENGTH_FLOOR`, carries NO anti-bot/block/JS-shell/blank fingerprint, and matches an empty-result phrase, the gate SHALL return `BlockVerdict.length_floor` annotated with `subsystem="empty_result"` — NOT a distinct wall verdict, and NOT an escalation signal.

The empty-result marker is a HINT, never an authority: it sharpens the terminal wording (`empty_unverified`) and is ONE necessary term in the promotion conjunction (`is_confirmed_empty`), but it SHALL NOT by itself promote a fetch to `ok` and SHALL NOT suppress any wall verdict. The empty-marker branch SHALL run AFTER every anti-bot/block/JS-shell/blank branch (a walled body that also happens to contain "no results" text keeps its wall verdict) and produces only the `subsystem` annotation on the otherwise-bare `length_floor` fallthrough.

#### Scenario: A thin "no results" body is annotated empty_result

- **WHEN** the gate evaluates a sub-floor `text/html` body with no wall/JS-shell/blank fingerprint that matches an empty-result phrase
- **THEN** `verdict == BlockVerdict.length_floor` with `subsystem == "empty_result"` and NO escalation signal

#### Scenario: A walled body that mentions "no results" keeps its wall verdict

- **WHEN** the gate evaluates a sub-floor body matching BOTH an anti-bot/block fingerprint AND an empty-result phrase
- **THEN** the wall branch wins (`anti_bot` / `block_page_detected`), NOT the `empty_result` annotation

#### Scenario: The empty marker never escalates or promotes at the gate

- **WHEN** the gate annotates a body `subsystem="empty_result"`
- **THEN** the `BlockResult` carries no `EscalationSignal` and no `ok` promotion — the gate's job ends at the annotation

### Requirement: The block catalogue covers bounded bespoke-wall phrases

`_BLOCK_PATTERNS` SHALL include high-precision phrases for the bounded set of common bespoke walls that today fall through to a bare `length_floor` — at minimum a PerimeterX interstitial ("pardon the interruption"), a generic "access denied", and "request unsuccessful" (Incapsula/Imperva). A sub-floor body matching one SHALL return `BlockVerdict.block_page_detected` (a hard wall), so a genuinely-walled bespoke interstitial is not downgraded to the thin/empty hedge. The catalogue is bounded on purpose: the wall space converges on a small number of mitigation vendors, unlike the open-ended empty-result phrasing space (which is therefore NOT catalogued as a promotion authority).

#### Scenario: A PerimeterX interstitial is a hard wall

- **WHEN** the gate evaluates a sub-floor body containing "Pardon the interruption"
- **THEN** `verdict == BlockVerdict.block_page_detected` (a hard wall), NOT a bare `length_floor`
