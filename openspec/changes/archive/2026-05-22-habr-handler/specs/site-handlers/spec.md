## ADDED Requirements

### Requirement: Habr handler renders article and threaded comments from the kek/v2 API

The system SHALL provide `HabrHandler` matching Habr article URLs — `https?://habr.com/(ru|en)/articles/<id>/`, `https?://habr.com/(ru|en)/companies/<slug>/articles/<id>/`, and the legacy `https?://habr.com/(ru|en)/post/<id>/` and `https?://habr.com/(ru|en)/company/<slug>/blog/<id>/` forms (case-insensitive; trailing slash optional). The handler SHALL fetch `https://habr.com/kek/v2/articles/<id>/` and `https://habr.com/kek/v2/articles/<id>/comments/` — both with `fl` / `hl` query parameters derived from the URL's language segment — and populate `TierResult.pre_rendered` with `content_md` (the article body rendered from `textHtml`, followed by a `## Discussion` section rendering the comment tree **threaded** — indented by reply depth, each comment carrying its author), `title` (from `titleHtml`), `byline` (the article author), and `headings`.

#### Scenario: Article URL renders body and threaded discussion

- **WHEN** the URL is a Habr article and both `kek/v2` endpoints return valid JSON
- **THEN** the handler returns `verdict == Verdict.ok`, `pre_rendered.content_md` contains the article body and a `## Discussion` section, and nested replies are indented by depth

#### Scenario: Comments endpoint failure degrades to article-only

- **WHEN** the article endpoint succeeds but the comments endpoint returns a non-200 or malformed JSON
- **THEN** the handler returns `verdict == Verdict.ok` with the article body and no `## Discussion` section, and does not raise

#### Scenario: Unknown article id falls through

- **WHEN** the `kek/v2` article endpoint returns a non-200 or an error payload for an unknown id
- **THEN** the handler returns `verdict == Verdict.not_found` so the orchestrator falls through to the generic path

#### Scenario: Language segment selects the API locale

- **WHEN** the URL's language segment is `/en/`
- **THEN** the `kek/v2` requests carry `fl=en&hl=en`; when the segment is `/ru/` or absent they carry `fl=ru&hl=ru`
