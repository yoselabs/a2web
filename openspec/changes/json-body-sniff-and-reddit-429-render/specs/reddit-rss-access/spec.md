## MODIFIED Requirements

### Requirement: RSS rate limiting is retryable, not terminal

The handler SHALL back off on Reddit RSS `429` responses and reuse `http_cache`; a `429` SHALL be treated as retryable. If retries are exhausted, a `429` on a **search or listing** surface SHALL escalate to a paid site render (identical to the `403` wall case — a rate-limited RSS surface is a wall), returning `escalate_to_render`. A `429` on a **thread/permalink** surface, when retries are exhausted, SHALL fail loud with `rate_limited` (retrieval-completeness contract), never a silent empty result.

#### Scenario: Burst 429 backs off then caches

- **WHEN** repeated RSS requests to one host return `429`
- **THEN** the handler backs off between attempts and reuses `http_cache` for the retries

#### Scenario: Search/listing 429 escalates to a paid render

- **WHEN** the Reddit RSS fetch for a `/search/` or listing URL returns `429` and the bounded backoff is exhausted
- **THEN** the handler returns a `TierResult` with `escalate_to_render` set (non-authoritative `block_page_detected`, no eager `try_user_browser` hint)

#### Scenario: Thread 429 fails loud

- **WHEN** the Reddit RSS fetch for a comments/permalink URL returns `429` and the bounded backoff is exhausted
- **THEN** the handler returns `Verdict.rate_limited` (fail loud), NOT a render escalation

### Requirement: A walled Reddit search/listing escalates to a paid site render

When Reddit's keyless RSS returns a wall on a search or listing surface — a hard block (`403`) OR a rate limit (`429`, after the bounded backoff is exhausted) — the handler SHALL escalate to a paid site render rather than fail loud with an eager wall hint. It returns a result carrying `escalate_to_render` (non-authoritative `block_page_detected`, no `try_user_browser` hint), so the orchestrator renders the original URL via the paid tier (Zyte `browserHtml`, which reads Reddit search fine). If no paid tier is keyed, the orchestrator's never-silently-miss guarantee still fires. Thread surfaces (comments/permalink) keep their existing handling (403 → archive escalation; 429 → fail loud with `rate_limited`).

#### Scenario: Search 403 escalates to a paid render, not an eager wall

- **WHEN** the Reddit RSS fetch for a `/search/` or listing URL returns `403`
- **THEN** the handler returns a `TierResult` with `escalate_to_render` set
- **AND** the result does NOT carry an eager `try_user_browser` operator hint (the render is tried first)

#### Scenario: Search 429 escalates to a paid render

- **WHEN** the Reddit RSS fetch for a `/search/` or listing URL returns `429` (backoff exhausted)
- **THEN** the handler returns a `TierResult` with `escalate_to_render` set

#### Scenario: Thread 403 is unchanged

- **WHEN** the Reddit RSS fetch for a comments/permalink URL returns `403`
- **THEN** the handler still escalates via the archive signal (not the paid render), preserving existing thread behavior
