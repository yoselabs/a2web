## ADDED Requirements

### Requirement: A walled Reddit search/listing escalates to a paid site render

When Reddit's keyless RSS returns a hard block (`403`) on a search or listing surface — Reddit rate-limits/blocks unauthenticated RSS — the handler SHALL escalate to a paid site render rather than fail loud with an eager wall hint. It returns a result carrying `escalate_to_render` (non-authoritative `block_page_detected`, no `try_user_browser` hint), so the orchestrator renders the original URL via the paid tier (Zyte `browserHtml`, which reads Reddit search fine). If no paid tier is keyed, the orchestrator's never-silently-miss guarantee still fires. Thread surfaces (comments/permalink) keep their existing 403 handling (archive escalation).

#### Scenario: Search 403 escalates to a paid render, not an eager wall

- **WHEN** the Reddit RSS fetch for a `/search/` or listing URL returns `403`
- **THEN** the handler returns a `TierResult` with `escalate_to_render` set
- **AND** the result does NOT carry an eager `try_user_browser` operator hint (the render is tried first)
- **AND** the verdict is a non-authoritative `block_page_detected` (it never ends the run on its own)

#### Scenario: Thread 403 is unchanged

- **WHEN** the Reddit RSS fetch for a comments/permalink URL returns `403`
- **THEN** the handler still escalates via the archive signal (not the paid render), preserving existing thread behavior
