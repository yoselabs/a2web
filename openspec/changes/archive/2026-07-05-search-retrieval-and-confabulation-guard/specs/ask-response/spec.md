## ADDED Requirements

### Requirement: confidence reflects the extractor obstacle signal on ask

On the `ask` path, `confidence` MUST NOT be derived solely from `(verdict, content length)`. When the extractor reports an `obstacle`, the response SHALL downgrade confidence: an `obstacle` in `{empty, blocked, paywalled, error}` caps `confidence` at `low`. The downgrade is one-directional — an `obstacle` may only lower confidence, never raise it. Because `obstacle` is produced after the base response is built (in the answer-extraction phase), this reconciliation is applied where `obstacle` reaches the wire (the ask-path projection), and applies only to `ask` (the `fetch_raw` envelope has no `obstacle`).

#### Scenario: Empty obstacle caps a would-be high confidence

- **WHEN** an `ask` fetch returns `verdict == ok` over more than 2000 characters of rendered content (which alone would yield `confidence: high`) but the extractor reports `obstacle: "empty"`
- **THEN** the wire `confidence` is `low`

#### Scenario: Blocked obstacle caps confidence

- **WHEN** an `ask` fetch reports `obstacle: "blocked"`
- **THEN** the wire `confidence` is `low`

#### Scenario: Healthy page keeps its computed confidence

- **WHEN** an `ask` fetch returns `verdict == ok` over rich content and the extractor omits `obstacle` (healthy page)
- **THEN** `confidence` is unchanged from its `(verdict, content length)` derivation

#### Scenario: fetch_raw is unaffected

- **WHEN** a `fetch_raw` request completes
- **THEN** confidence derivation is unchanged — no `obstacle` reconciliation is applied (fetch_raw carries no obstacle)
