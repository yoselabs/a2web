## Context

Probe results (curl_cffi, anonymous):

- `GET linux.do/latest.json` → `200 application/json` — keys `users`, `primary_groups`, `topic_list` (`topic_list.topics[]` each with `id`, `title`, `posts_count`, …).
- `GET meta.discourse.org/latest.json` → `200`, **identical shape** — confirms the contract is engine-wide.
- `GET meta.discourse.org/t/<id>.json` → `200` — keys `post_stream` (`post_stream.posts[]` each with `username`, `name`, `cooked` (rendered post HTML), `post_number`, `reply_to_post_number`, `created_at`), `tags`, `fancy_title`.

Discourse exposes `.json` on every routable URL. The post stream's `reply_to_post_number` gives the reply tree; `cooked` is the post body as HTML.

## Goals / Non-Goals

**Goals:**
- One handler covering every Discourse forum via the engine-wide JSON contract.
- Threaded topic rendering; topic-list rendering with `next_links`.
- Browser-free, anti-bot-free (the `.json` API is not bot-gated the way the HTML is).

**Non-Goals:**
- Zero-config host detection — v1 uses a configured allowlist (see Open Questions).
- Authenticated / login-gated Discourse content — the handler fetches what the anonymous `.json` returns.

## Decisions

### D1 — Config allowlist for `matches()`, not a URL-shape sniff
Discourse runs on arbitrary domains, so `matches(url)` cannot key on host alone. A topic URL has a distinctive `/t/<slug>/<id>` shape, but a forum *index* URL (host root, `/latest`, `/c/<cat>`) is not distinctive at all — so a pure URL-shape sniff cannot claim listing pages. v1 uses `AppSettings.discourse_hosts`, an allowlist (env `A2WEB_DISCOURSE_HOSTS`), defaulting to `linux.do` + `meta.discourse.org`. This is idiomatic a2web (settings-driven, like the proxy pool and route rules), safe (no false matches), and still engine-level leverage — adding a forum is one config line, never code.

### D2 — The `.json` twin, not HTML scraping
Every Discourse URL `U` has a JSON twin: a topic at `U.json`, a forum index at `<host>/latest.json`. The handler appends `.json` (topic) or fetches `latest.json` (index). No HTML parsing of the SPA shell.

### D3 — Topic vs index dispatch on the path
`matches()` having claimed the host, `fetch()` branches on the path: `/t/...` ending in a numeric id → topic; otherwise (host root, `/latest`, `/c/<category>`) → forum index via `latest.json`.

### D4 — Threaded topic render via `reply_to_post_number`
`post_stream.posts[]` is a flat array; `reply_to_post_number` links each post to its parent. Build the reply tree, render **threaded** — indentation by reply depth, each post carrying its `username`. `cooked` (post HTML) → markdown. `byline` = the first post's author.

### D5 — Index render → records + `next_links`
`latest.json`'s `topic_list.topics[]` → a record list in `content_md`, and one `discussion` `NextLink` per topic (`<host>/t/<slug>/<id>`).

### D6 — Routine-failure contract
Per the existing `Handlers MUST NOT raise on routine HTTP failures` requirement: a non-200 / malformed-JSON response → `verdict == Verdict.not_found` so the orchestrator falls through. A configured host that turns out not to be Discourse (no `topic_list` / `post_stream` in the JSON) → `not_found`, never a raise.

### D7 — Settings reach `matches()` by threading through `match_handler`
`DiscourseHandler.matches()` needs the `discourse_hosts` allowlist, but the
`Handler.matches(url)` protocol was settings-free. The chosen fix threads
settings through: `Handler.matches(self, url, settings=None)` and
`match_handler(url, settings=None)` gain an **optional** `settings` parameter;
`SiteHandlerTier.fetch` passes `state.settings`. The optionality keeps it
backward-compatible — the five existing pure-URL handlers add an ignored
`settings` parameter and every existing `match_handler(url)` / `handler.matches(url)`
call site (≈40, mostly tests) keeps working unchanged. `DiscourseHandler.matches`
uses `settings.discourse_hosts` when given, falling back to the shared
`DEFAULT_DISCOURSE_HOSTS` default when `settings is None`. **Alternative
rejected:** an `os.environ` read inside `matches()` — it would honour the env
var but silently miss a YAML-only `discourse_hosts` override. This also makes
the settings-aware path available to `TwitterHandler`, whose `matches()`
carries the same documented "state isn't reachable here" wart (not refactored
in this change — its behaviour is left identical).

## Risks / Trade-offs

- **Allowlist friction** — a new Discourse forum needs a config entry before the handler claims it → Mitigation: accepted for v1; the defaults cover the named target (`linux.do`); D1's Open Question tracks a zero-config path.
- **Login-gated content** — some Discourse categories require auth → Mitigation: the handler renders what anonymous `.json` returns; gated topics degrade to `not_found` and fall through.
- **Cloudflare on the JSON endpoint** — `.json` could itself be challenged → Mitigation: the probe got clean 200s anonymously; if a forum challenges, the routine-failure contract falls through to the raw/browser tiers.

## Migration Plan

1. `AppSettings.discourse_hosts` field + env binding.
2. `handlers/discourse.py` — `matches()` (allowlist), `fetch()` (topic vs index dispatch), threaded render, index render.
3. Recorded JSON fixtures (`latest.json`, `t/<id>.json` with a nested reply); handler tests; register in `match_handler` order.
4. `make check` green.

No envelope change. Rollback: unregister the handler — Discourse URLs fall back to the raw/browser path.

## Open Questions

- Zero-config matching: `matches()` could claim any host with a `/t/<slug>/<digits>` topic path and let `fetch()` confirm via the `.json` shape (returning `no_match` if not Discourse). That covers topic pages with no config, but not forum-index pages. Revisit if the allowlist proves to be real friction.
- Whether the threaded renderer is shared with `structural-record-detection` / `habr-handler` — defer to a follow-up refactor once all have landed.
