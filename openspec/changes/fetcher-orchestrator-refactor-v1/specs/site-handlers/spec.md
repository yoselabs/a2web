## ADDED Requirements

### Requirement: The FetchVerdict→Verdict mapping is centralized in a shared helper

A new module `src/a2web/handlers/_common.py` SHALL expose a pure helper:

```python
def map_non_ok(outcome: FetchOutcome, *, url: str) -> TierResult | None:
    """Map a non-ok FetchOutcome to a TierResult via the standard
    FetchVerdict → Verdict table. Returns None when outcome.verdict is
    FetchVerdict.ok (caller continues). Returns a TierResult carrying
    Verdict.timeout / not_found / rate_limited / connection_error otherwise."""
```

All site handlers in `src/a2web/handlers/` (reddit, github, hn, arxiv, wikipedia, lobste, twitter, v2ex, habr, discourse) SHALL call this helper for the standard non-ok short-circuit at the top of their `fetch()` body. The previously repeated 4-line block (one `if outcome.verdict is FetchVerdict.<x>` per non-ok value) SHALL be removed.

The helper covers the homogeneous part of handler-level outcome interpretation. Handler-specific policy (Reddit's `status_code == 403` branch dispatching to archive escalation for threads vs. connection_error for listings) SHALL remain INLINE in that handler — it is the only handler with shape-aware HTTP-status policy, and inventing a generic role-keyed abstraction for one caller is the wrong shape.

#### Scenario: Every handler uses `map_non_ok` for the standard non-ok cases

- **WHEN** a handler receives `FetchOutcome` with `verdict is not FetchVerdict.ok`
- **THEN** it short-circuits via `map_non_ok(outcome, url=url)`; the previously hand-written 4-line `if/elif` block is gone

#### Scenario: Reddit's 403 policy stays inline

- **WHEN** Reddit handler receives `outcome.status_code == 403` after `map_non_ok` returned None (i.e. the underlying FetchVerdict was ok but the upstream HTTP layer surfaced a 403)
- **THEN** the Reddit-specific `if shape in ("search", "listing"): connection_error else: archive_escalation` branch fires inline — this is Reddit-only policy and is NOT pulled into the shared helper

#### Scenario: A new handler adopts the helper without reinventing the FetchVerdict mapping

- **WHEN** a new site handler is added (e.g. for Stack Overflow)
- **THEN** its non-ok short-circuit routes through `map_non_ok`; the FetchVerdict → Verdict policy is unchanged across handlers
