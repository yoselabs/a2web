## MODIFIED Requirements

### Requirement: Report content excludes raw URL, query, and page content by default

A feedback report SHALL include the hint `code`, `severity`, `fix` (when
present), the full per-fetch escalation history (one entry per tier/handler
attempt, each carrying its source, verdict, and duration — not only the
terminal step), the fetch's terminal response context (status code, content
type, cache state, tier used), the operation kind (`query` or `fetch_raw`),
and the a2web version. A feedback report SHALL NOT include the raw fetched
URL (requested or final), the caller's query text, or any URL embedded
within the hint's free-text message, unless a separate, independently-off-
by-default "include content" setting is enabled. When that setting is
enabled, it SHALL govern every field capable of carrying a URL or query
text — including the hint message — not only a distinct url/query field
pair.

#### Scenario: Default report omits URL and content

- **WHEN** feedback reporting is enabled (content-inclusion setting left at its default of off) and a report is emitted for a failed fetch whose hint message names the URL that failed
- **THEN** the outgoing payload contains no raw URL or query text in any field, including the hint's message text

#### Scenario: Explicit opt-up includes content

- **WHEN** both feedback reporting and the separate content-inclusion setting are enabled
- **THEN** the outgoing payload includes the fetched URL, query, and the hint's message text with any URL it names left intact

#### Scenario: Default report still includes the escalation chain and response context

- **WHEN** feedback reporting is enabled (content-inclusion setting at its default of off) and a fetch tried more than one tier before resolving
- **THEN** the outgoing payload includes an entry for every tier/handler attempt made (not only the last), plus the fetch's terminal status code, content type, cache state, and tier used — none of which name a URL or query text
