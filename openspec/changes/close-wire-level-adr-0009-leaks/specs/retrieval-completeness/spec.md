## ADDED Requirements

### Requirement: A degraded sub-fetch is never rendered as an absent section

Where a handler assembles its output from several upstream calls, a call that
fails SHALL NOT be rendered as though the section it would have populated were
empty at the source. The handler SHALL either fail the fetch or attach an
operator hint naming the section that could not be retrieved.

Rendering an issue with zero comments because the comments call was
rate-limited is indistinguishable, to a caller that never sees the body, from an
issue that genuinely has no comments. That is the ADR-0009 silent miss, and it
is sharpened by the empty-vs-wall invariant: an unverified empty must never be
promoted to a confident "there is nothing here".

#### Scenario: A rate-limited sub-fetch is declared

- **WHEN** a handler's supplementary call fails and its section renders empty
- **THEN** the response carries an operator hint naming that section as
  unretrieved, and the emptiness is not presented as a property of the source

#### Scenario: A genuinely empty section is not flagged

- **WHEN** every upstream call succeeds and a section is legitimately empty
- **THEN** no unretrieved-section hint is emitted

### Requirement: paid_auth_error carries an operator hint naming the fix

A terminal `paid_auth_error` verdict SHALL emit a `critical` operator hint that
names the misconfigured key and the remediation step. The ADR-0009 floor already
seeds `retrieval_incomplete` for this verdict on the stated grounds that it
"keeps its OWN dedicated hint" in place of `try_user_browser`; that hint SHALL
exist.

A guard MAY exempt `paid_auth_error` from the `try_user_browser` requirement
only by asserting the presence of this hint. An exemption justified by a comment
naming a hint that is never constructed is not an exemption; it is an unchecked
hole, and this is how the present one survived.

#### Scenario: A bad paid key names its own fix

- **WHEN** a keyed paid tier returns an authentication failure
- **THEN** the envelope carries `status: failed`, `retrieval_incomplete: true`,
  and a `critical` operator hint identifying the key and the fix

#### Scenario: The terminal-hint guard checks the hint it exempts on

- **WHEN** the terminal-hint coherence guard exempts a terminal outcome from the
  `try_user_browser` requirement because another hint covers it
- **THEN** the guard asserts that the other hint is actually emitted
