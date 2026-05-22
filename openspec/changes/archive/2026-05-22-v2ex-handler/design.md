## Context

Probe results (curl_cffi, anonymous):

- `GET www.v2ex.com/api/topics/latest.json` → `200 application/json` — `list[40]`, each item `{node, member, title, url, content, created, …}`.
- `GET www.v2ex.com/api/topics/show.json?id=<id>` → `200` — `list[1]`, the topic (`title`, `content`, `content_rendered`, `member`, `created`, `replies`, `url`).
- `GET www.v2ex.com/api/replies/show.json?topic_id=<id>` → `200` — a flat array of replies (`content`, `content_rendered`, `member`, `created`).

The API v1 is open, unauthenticated, read-only — it predates the token-gated v2 API and remains stable. The CN-forum spike separately confirmed a raw-HTML fetch of a V2EX topic is unreliable (a stripped ~275-char page), so the API is the path.

## Goals / Non-Goals

**Goals:**
- Reliable V2EX topic extraction via the open API, bypassing the stripped-HTML problem.
- Topic body + replies in one `pre_rendered` result.

**Non-Goals:**
- V2EX node / index pages — out of scope for v1; topic pages are the high-value case.
- The token-gated v2 API — v1 covers read access with no credentials.

## Decisions

### D1 — API, not HTML
A raw fetch of a V2EX topic returns a stripped page (spike-confirmed). `topics/show.json` + `replies/show.json` are the clean source. This is the established `reddit` / `hn` handler pattern.

### D2 — Parallel fetch of topic + replies
The two endpoints are independent GETs — fetch them concurrently in an `anyio` task group (the `archive.py` pattern).

### D3 — `matches()` keys on the V2EX topic URL
`https?://(www\.)?v2ex.com/t/<id>` — the numeric `<id>` is what both API calls need; a trailing slug or `#reply` fragment is ignored.

### D4 — Linear replies, no threading
V2EX replies are a flat chronological list — there is no parent/child reply structure in the API. Render `## Replies` as a flat ordered list, each reply prefixed with its author. (Contrast Discourse / Habr, which carry a reply tree — V2EX has none, so no depth render.)

### D5 — Routine-failure contract
Per the existing `Handlers MUST NOT raise on routine HTTP failures` requirement: a non-200 / empty-`list` topic response → `verdict == Verdict.not_found` (fall through); a failed *replies* fetch → render the topic alone, no `## Replies` section, no raise.

## Risks / Trade-offs

- **API v1 deprecation** — V2EX could retire v1 in favour of the token-gated v2 → Mitigation: v1 has been stable for years; isolated to one handler; the routine-failure contract degrades to the generic path. A handler test against a recorded fixture catches a shape change in CI.
- **Rate limiting** — V2EX rate-limits the API per IP → Mitigation: out of scope for the handler itself; a2web's existing per-host circuit breaker absorbs sustained failures, and routine-failure falls through.

## Migration Plan

1. `handlers/v2ex.py` — `V2EXHandler` with `matches()` + `fetch()` (parallel `topics/show` + `replies/show`).
2. Render topic body + linear `## Replies`; `byline` = topic author.
3. Recorded JSON fixtures; handler tests; register in `match_handler` order.
4. `make check` green.

No envelope change. Rollback: unregister the handler — V2EX URLs fall back to the raw path.

## Open Questions

- Whether to also handle V2EX node / index URLs via `topics/latest.json` or a node feed — deferred until there is a concrete need; topic pages are the v1 scope.
