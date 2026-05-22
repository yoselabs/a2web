## Why

V2EX is a major Chinese-language developer forum and a frequent fetch target. A raw-HTML fetch of V2EX is unreliable — the spike found V2EX serves stripped pages to anonymous scrapers (a topic page returned ~275 chars). But V2EX's API v1 is **open and unauthenticated**: a probe confirmed `api/topics/show.json?id=<id>` returns the topic and `api/replies/show.json?topic_id=<id>` returns its replies. The API is the clean, reliable path — the same pattern the `reddit` / `hn` handlers already use.

## What Changes

- **New `V2EXHandler`** (Strategy + Registry tier-0 handler). `matches()` claims V2EX topic URLs — `https?://(www\.)?v2ex.com/t/<id>` (with optional `#reply` fragment / trailing slug).
- The handler fetches `https://www.v2ex.com/api/topics/show.json?id=<id>` and `https://www.v2ex.com/api/replies/show.json?topic_id=<id>` in parallel, and populates `TierResult.pre_rendered` with `content_md` (the topic body followed by a `## Replies` section), `title`, `byline` (the topic author).
- V2EX replies are **linear** (not threaded) — the `## Replies` section is a flat, ordered list, each reply carrying its author. No depth.
- No browser tier, no new dependency.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `site-handlers`: adds the `V2EXHandler` requirement — a tier-0 handler matching V2EX topic URLs and rendering topic + linear replies from the open API v1.

## Impact

- New `src/a2web/handlers/v2ex.py`; registered in `match_handler` declaration order.
- No new dependencies — `curl_cffi` covers the JSON fetch.
- API v1 is unauthenticated read-only and stable (it long predates the token-gated v2 API); the handler's routine-failure contract degrades to the generic path rather than raising.
