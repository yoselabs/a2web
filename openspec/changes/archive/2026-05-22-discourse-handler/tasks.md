## 1. Settings

- [x] 1.1 Add `AppSettings.discourse_hosts: list[str]` — env `A2WEB_DISCOURSE_HOSTS`, default `["linux.do", "meta.discourse.org"]`; YAML-overridable like the other list settings.

## 2. Handler implementation

- [x] 2.1 New `src/a2web/handlers/discourse.py` — `DiscourseHandler.matches(url)` returns `True` when the URL host is in `discourse_hosts`.
- [x] 2.2 `fetch()` path dispatch — `/t/<slug>/<id>` (or `/t/<id>`) → topic; host root / `/latest` / `/c/<category>` → forum index.
- [x] 2.3 Topic render — fetch `<url>.json`, build the reply tree from `post_stream.posts[].reply_to_post_number`, render threaded (depth-indented, per-post author), `cooked` HTML → markdown; `title` from `fancy_title`, `byline` from the first post.
- [x] 2.4 Index render — fetch `latest.json`, render `topic_list.topics[]` as a record list, emit one `discussion` `NextLink` per topic.
- [x] 2.5 Routine-failure handling — non-200 / JSON lacking `post_stream` / `topic_list` → `Verdict.not_found`, no raise.
- [x] 2.6 Register `DiscourseHandler` in the handler registry / `match_handler` declaration order.

## 3. Tests

- [x] 3.1 Recorded JSON fixtures — a `t/<id>.json` (with a nested reply) and a `latest.json`.
- [x] 3.2 Handler tests — topic URL renders a threaded post stream; forum index emits one `discussion` `NextLink` per topic; a non-allowlisted host is not matched; a configured host returning non-Discourse JSON → `not_found` without raising.
- [x] 3.3 `match_handler` resolves a configured-host topic URL to `DiscourseHandler`.

## 4. Verify

- [x] 4.1 `make check` green — lint, `ty`, full suite, coverage ≥ 85%.
