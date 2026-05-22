## ADDED Requirements

### Requirement: Discourse handler renders topics and forum indexes from the .json endpoints

The system SHALL provide `DiscourseHandler` matching URLs whose host is in the configured `AppSettings.discourse_hosts` allowlist (env `A2WEB_DISCOURSE_HOSTS`; default includes `linux.do` and `meta.discourse.org`). For a **topic** URL (path `/t/<slug>/<id>` or `/t/<id>`) the handler SHALL fetch `<topic-url>.json` and populate `TierResult.pre_rendered` with `content_md` (the `post_stream` rendered **threaded** via `reply_to_post_number` — indented by reply depth, each post carrying its author), `title` (`fancy_title`), and `byline` (the first post's author). For a **forum-index** URL (host root, `/latest`, or `/c/<category>`) the handler SHALL fetch `latest.json` and populate `content_md` with the topic list and `next_links` with one `discussion` candidate per topic.

#### Scenario: Topic URL renders a threaded post stream

- **WHEN** the URL is a topic on a configured Discourse host and `<url>.json` returns a valid `post_stream`
- **THEN** the handler returns `verdict == Verdict.ok` and `pre_rendered.content_md` renders the posts threaded, replies indented under their parent post

#### Scenario: Forum index renders the topic list with next_links

- **WHEN** the URL is the index / `/latest` of a configured Discourse host
- **THEN** the handler fetches `latest.json` and emits one `discussion` `NextLink` per topic

#### Scenario: Non-allowlisted host is not claimed

- **WHEN** the URL's host is not in `discourse_hosts`
- **THEN** `DiscourseHandler.matches()` returns `False` and the handler does not claim the URL

#### Scenario: Configured host that is not Discourse falls through

- **WHEN** a configured host returns JSON without `post_stream` / `topic_list`, or a non-200
- **THEN** the handler returns `verdict == Verdict.not_found` and does not raise
