## ADDED Requirements

### Requirement: HN front page renders both article and discussion URLs

For each external-link story on the Hacker News front page, the `HNHandler` SHALL emit, in `content_md`, both the article URL and the story's Hacker News discussion URL (`https://news.ycombinator.com/item?id=<objectID>`). For text-only stories (no external URL), the discussion URL SHALL be the single URL emitted. The `next_links` array SHALL carry one `NextLink` per story (the article URL for external-link stories, the discussion URL for text-only stories) — it SHALL NOT emit a second `NextLink` for the discussion URL.

#### Scenario: external-link story exposes both URLs in content

- **WHEN** the HN handler renders a front-page fixture containing an external-link story
- **THEN** that story's line in `content_md` contains both the external article URL and the `https://news.ycombinator.com/item?id=<objectID>` discussion URL

#### Scenario: text-only story exposes the discussion URL

- **WHEN** the HN handler renders a front-page fixture containing a text-only story (no `url` field)
- **THEN** that story's line in `content_md` contains the `https://news.ycombinator.com/item?id=<objectID>` discussion URL

#### Scenario: next_links stays one entry per story

- **WHEN** the HN handler renders a front-page fixture with N external-link stories
- **THEN** `next_links` contains at most one `NextLink` per story and no discussion-URL duplicate entry
