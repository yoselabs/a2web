## ADDED Requirements

### Requirement: V2EX handler renders topic and replies from the open API v1

The system SHALL provide `V2EXHandler` matching V2EX topic URLs — `https?://(www\.)?v2ex\.com/t/<id>` (case-insensitive; a trailing slug or `#reply` fragment is ignored). The handler SHALL fetch `https://www.v2ex.com/api/topics/show.json?id=<id>` and `https://www.v2ex.com/api/replies/show.json?topic_id=<id>` and populate `TierResult.pre_rendered` with `content_md` (the topic body followed by a `## Replies` section rendering the replies as a flat, chronologically ordered list, each reply carrying its author), `title` (the topic title), and `byline` (the topic author).

#### Scenario: Topic URL renders body and replies

- **WHEN** the URL is a V2EX topic and both API endpoints return valid JSON
- **THEN** the handler returns `verdict == Verdict.ok`, `pre_rendered.content_md` contains the topic body and a `## Replies` section, and replies are a flat ordered list

#### Scenario: Replies endpoint failure degrades to topic-only

- **WHEN** the topic endpoint succeeds but the replies endpoint returns a non-200 or malformed JSON
- **THEN** the handler returns `verdict == Verdict.ok` with the topic body and no `## Replies` section, and does not raise

#### Scenario: Unknown topic id falls through

- **WHEN** `api/topics/show.json` returns an empty list for an unknown id
- **THEN** the handler returns `verdict == Verdict.not_found` so the orchestrator falls through to the generic path
