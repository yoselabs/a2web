## ADDED Requirements

### Requirement: The browser smoke check fails rather than skips when it is required

Where the browser smoke check is required by configuration, an unavailable
browser binary SHALL fail the check. It SHALL NOT auto-skip.

An auto-skip under a required flag is how a dead engine rung goes unnoticed: the
check reports success by not running, and the collapse of one rung onto another
is invisible. That failure has occurred and the hard-fail behaviour is what
closes it.

This specification previously required the opposite. An implementer following it
would re-open the hole the current guard closes, which is the sharper form of
spec drift: the specification is not merely stale, it prescribes a regression.

#### Scenario: A required smoke check fails on a missing binary

- **WHEN** the smoke check is required and the browser binary is unavailable
- **THEN** the check fails

#### Scenario: An unrequired smoke check may skip

- **WHEN** the smoke check is not required
- **THEN** it may skip on an unavailable binary
