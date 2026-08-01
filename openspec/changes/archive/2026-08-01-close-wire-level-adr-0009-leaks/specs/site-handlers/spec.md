## ADDED Requirements

### Requirement: A handler that extracts prose from HTML runs the challenge check

Any handler path that retrieves HTML and derives its content by generic text
extraction SHALL run the shared `challenge_verdict` check on the raw HTML before
returning `Verdict.ok`. A challenge or interstitial page extracts to plausible
prose and clears every length floor, so extraction success is not evidence of
retrieval success.

This SHALL be enforced structurally rather than by convention. The bound is
currently present on two such paths (`twitter`, `wikipedia`) and absent on a
third (`reddit`'s `old.reddit` fallback) that is otherwise the same shape — the
failure mode where a missing bound is invisible next to siblings that have it.

#### Scenario: An interstitial is not laundered into ok

- **WHEN** a handler GETs HTML that is a block or challenge page, and generic
  extraction yields non-empty prose from it
- **THEN** the handler returns a wall verdict, not `Verdict.ok`

#### Scenario: The check cannot be omitted from a new path

- **WHEN** a handler path retrieves HTML and calls a generic prose extractor
  without invoking the shared challenge check
- **THEN** the offline suite fails, naming that path
