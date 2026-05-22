## 1. Handler implementation

- [x] 1.1 New `src/a2web/handlers/v2ex.py` — `V2EXHandler.matches(url)` claims `https?://(www\.)?v2ex.com/t/<id>`, extracting the numeric id.
- [x] 1.2 Implement `fetch()` — parallel `anyio` task-group GETs of `api/topics/show.json?id=<id>` and `api/replies/show.json?topic_id=<id>`.
- [x] 1.3 Render the topic — title, body (`content` / `content_rendered` → markdown), `member` → `byline`.
- [x] 1.4 Render replies — a flat, chronologically ordered `## Replies` section, each reply prefixed with its author.
- [x] 1.5 Routine-failure handling — topic endpoint non-200 / empty list → `Verdict.not_found`; replies endpoint failure → topic-only, no raise.
- [x] 1.6 Register `V2EXHandler` in the handler registry / `match_handler` declaration order.

## 2. Tests

- [x] 2.1 Recorded JSON fixtures — one `topics/show.json` response, one `replies/show.json` response.
- [x] 2.2 Handler tests — topic URL renders body + flat `## Replies`; replies-endpoint failure degrades to topic-only without raising; unknown id → `not_found`.
- [x] 2.3 `match_handler` resolves a V2EX topic URL to `V2EXHandler`; a non-V2EX URL does not.

## 3. Verify

- [x] 3.1 `make check` green — lint, `ty`, full suite, coverage ≥ 85%.
