## Why

Discourse is one of the most widely deployed forum engines — `linux.do` (a large Chinese-language developer community) and thousands of other forums run it. Every Discourse URL serves a JSON twin: `<forum>/latest.json` (the topic list) and `<forum>/t/<id>.json` (a topic's full post stream, with `reply_to_post_number` giving the reply tree). A probe confirmed the JSON shape is identical on `linux.do` and `meta.discourse.org` — so a single handler keyed on the Discourse JSON contract covers **every** Discourse forum at once. This is engine-level leverage, not a per-site handler.

Discourse forums are also Cloudflare-fronted and partly client-rendered — a raw-HTML fetch is unreliable. The `.json` endpoints are the clean, stable path.

## What Changes

- **New `DiscourseHandler`** (Strategy + Registry tier-0 handler). Because Discourse runs on arbitrary domains, `matches()` claims URLs whose host is in a configured allowlist — `AppSettings.discourse_hosts` (env `A2WEB_DISCOURSE_HOSTS`); `linux.do` and `meta.discourse.org` ship as defaults.
- **Topic URLs** (`/t/<slug>/<id>` or `/t/<id>`) → fetch `<topic>.json`, render the post stream **threaded** via `reply_to_post_number`, `pre_rendered` carries `content_md` + `title` + `byline` (the first post's author).
- **Forum index / `/latest` / `/c/<category>` URLs** → fetch `latest.json`, render the topic list as records and populate `next_links` (one `discussion` candidate per topic).
- No new dependency, no browser tier.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `site-handlers`: adds the `DiscourseHandler` requirement — a tier-0 handler matching configured Discourse hosts, rendering topic post-streams (threaded) and forum topic-lists from the `.json` endpoints.

## Impact

- New `src/a2web/handlers/discourse.py`; registered in `match_handler` declaration order.
- New `AppSettings.discourse_hosts` field (env `A2WEB_DISCOURSE_HOSTS`, default `["linux.do", "meta.discourse.org"]`).
- No new dependencies — `curl_cffi` + `lxml` cover HTTP and `cooked`-HTML → markdown.
- Config-driven matching keeps it safe — no false matches on arbitrary hosts; adding a Discourse forum is a one-line config change, never code. A zero-config topic-URL-shape sniff is possible later (see design Open Questions).
