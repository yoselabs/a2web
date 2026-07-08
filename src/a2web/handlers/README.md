# Site handlers — tier-0 for known hosts

A handler is a `Tier` (carries `name` + async `fetch`) plus a synchronous
`matches(url) -> bool` discriminator. Handlers run before generic raw/jina/
browser tiers because they bypass HTML scraping entirely — they call the
site's structured API (Reddit's `.json`, HN Algolia, GitHub REST, Discourse
`/t/<slug>/<id>.json`, Habr `kek/v2`, V2EX `api/v1`, …) and render the result
into markdown directly.

Adding a handler: drop a module here, implement the `Handler` protocol, add
the instance to `_HANDLERS` in `__init__.py`.

## Transport discipline

**Every handler MUST call `fetch_bytes` from `a2web.packages.http_fetch`.**

No hand-rolled `httpx.AsyncClient`, no inline `curl_cffi` sessions. The
shared primitive gives every handler:

- Chrome120 TLS impersonation (`curl_cffi`) — without this, Cloudflare-fronted
  hosts like `linux.do` serve an anti-AI banner instead of the JSON payload.
- Proxy plumbing via `state.proxy_pool` when a route rule matches.
- Per-host circuit breakers via `state.breakers`.
- Closed-verdict mapping (`FetchVerdict` → `Verdict`) — no raw `httpx`
  exceptions escape into the orchestrator.

The reason this is a rule: when handlers forked their own transport, unit
tests monkeypatched the handler's `httpx.AsyncClient.get` seam. Those tests
looked green while production silently failed on Cloudflare hosts. Routing
everything through `fetch_bytes` means the test seam *is* the transport seam.

## Rendering HTML fragments

When a site's API returns HTML fragments (Discourse `cooked`, Habr `textHtml`,
V2EX `content_rendered`, HN Algolia `text`), use `to_markdown` /
`to_text` from `html_fragment` (the shelf package). Don't hand-roll regex
strippers — they miss HTML entities (the `&rsquo;` class of bug).

## Live probe

`make handler-probe` runs every registered handler against a real
representative URL in `src/a2web/handler_probe.py:_PROBE_URLS`. Adding a
handler **MUST** add a corresponding probe URL; the probe fails loudly when
a registered handler is missing from the map.

The probe is **not** in `make check` — it spends bandwidth and hits live
hosts. Run it deliberately when:

- adding a new handler,
- changing transport behavior (anything under `packages/http_fetch/`),
- changing the rendering pipeline for a handler.

A passing `make handler-probe` against `linux.do` is the empirical assertion
that the transport-unification work landed correctly.

### Known-flaky probe targets

Two probe URLs depend on external state and may fail without indicating a
handler regression:

- **reddit** — Reddit hardened its anti-bot in 2024-25; even curl_cffi
  impersonation gets 403 on archived `.json` URLs for unauthenticated
  clients. Unit tests cover the handler's `.json` → old.reddit fallback
  chain; the live probe surfaces the upstream block.
- **twitter** — depends on a working `nitter_instances` host. Public nitter
  has decayed since Twitter's API lockdown; expect `connection_error`
  unless you configure a private nitter mirror.

Both are environmental, not regressions. The architectural test of this
phase is **linux.do**, which exercises the curl_cffi-impersonated transport
path that previously failed.
