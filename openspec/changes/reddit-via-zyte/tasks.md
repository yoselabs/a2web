> Sequencing: group 1 (Zyte raw mode) and group 2 (URL normalization + old.reddit parser)
> are independent and can proceed in parallel; group 3 (eager routing + ladder) wires them
> together; group 4 (content-expectations) layers the honest-partial contract on top.
> Depends on `reddit-reachability-never-silent-miss` having landed (Zyte tier + RSS handler + never-silently-miss envelope).

## 1. Zyte raw fetch mode (paid-fetch-tiers)

- [ ] 1.1 Add a `mode` toggle to `ZyteTier` (`browserHtml` | `httpResponseBody`); in raw mode POST `{"url", "httpResponseBody": true}`, base64-decode the body, return as `TierResult` (content_type from response headers)
- [ ] 1.2 Keep the 401/402/403 → authoritative `paid_auth_error` fail-loud mapping identical in both modes; keep timeout/connection mapping
- [ ] 1.3 Allow the mode to be selected per-dispatch (handler/orchestrator picks raw for old.reddit); default stays `browserHtml`
- [ ] 1.4 Tests: raw mode decodes body + returns HTML; bad key → `paid_auth_error` STOP in raw mode; mode selection honored

## 2. Reddit URL normalization + old.reddit parser (reddit-content-access)

- [ ] 2.1 `normalize(url) -> (channel, canonical_url)`: thread/comments (www/old/np/new hosts, `redd.it/<id>`, `/r/<sub>/s/<share>`, `.json`/`.rss` variants) → `old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top`; listing/search/subreddit → new-reddit canonical. Reuse the prior change's short/share-link resolver. Never emit `.json`
- [ ] 2.2 old.reddit flat-HTML parser: `div.thing.comment` → author, score, body, nesting depth; the post header → title/author/score. Boundary-typed (in `packages/` or the handler), no shreddit web-components, trafilatura-independent
- [ ] 2.3 Read the comment-total oracle (confirm source during impl: old.reddit page header "N comments" vs new-reddit `shreddit-post[comment-count]`) — needed by group 4
- [ ] 2.4 Tests: normalization table for every input shape; parser on a captured old.reddit fixture yields structured scored/nested comments; oracle extracted

## 3. Eager Reddit routing + arbitration ladder (reddit-content-access + paid-fetch-tiers)

- [ ] 3.1 Reddit handler: route eagerly to the paid tier (raw mode for old.reddit) when a paid tier is configured, bypassing the free ladder; fall back to RSS when un-keyed. Never `.json`
- [ ] 3.2 Orchestrator/playbook: support handler-initiated eager paid dispatch (gated on paid-tier availability), alongside the existing last-resort escalation
- [ ] 3.3 Availability-gated ladder: public reads use operator policy order over `[self-hosted (Unavailable now), paid, RSS]`; gated content → self-hosted only (fail loud when absent). Add the operator policy-order knob (default: near-term `paid → RSS`; documented future `self-hosted → paid → RSS`)
- [ ] 3.4 Keep RSS handler as rung 3 (keyless fallback); keep the never-silently-miss critical hint on total failure
- [ ] 3.5 Tests: keyed → Reddit hits Zyte raw + old.reddit, not the free ladder; un-keyed → RSS; policy order honored; gated-content request without self-hosted rung fails loud

## 4. content-expectations honest-partial contract (content-expectations)

- [ ] 4.1 Define the expectation seam: `oracle()` + `progress()` → `ready | partial | fail` with tolerance; general, Reddit-first instance wired to the comment oracle
- [ ] 4.2 Reddit thread: on `partial`, emit `OperatorHint(code="comments_partial", severity="info", …)` + add `comments_loaded`/`comments_total` to the response model (additive; omit-when-empty). On zero-progress-vs-positive-oracle → never-silently-miss critical hint
- [ ] 4.3 Bounded satisfaction effort: for the Zyte/old.reddit path it is a pure post-fetch assertion (one load); reserve the ≤3-min action-loop budget in the seam for the future browser rung (design only, not built)
- [ ] 4.4 Tests: deep thread → `comments_loaded=458, comments_total=32346` + `comments_partial` hint; small thread within tolerance → `ready`, no hint; zero-vs-positive → critical hint

## 5. Docs + decision records

- [ ] 5.1 Update ADR-0011 (Reddit access strategy): Zyte-public validated (browserHtml + httpResponseBody on old.reddit); browser+cookies works but ONLY from residential IP; datacenter (shen/Contabo) blocked; the arbitration ladder + Zyte-primary/self-hosted-deferred decision
- [ ] 5.2 BACKLOG: the deferred self-hosted Camoufox/zendriver browser tier + bee/residential-egress rung (Unavailable-gated rung 1; enables free/private + logged-in). Reference the spike scripts in `docs/history/spikes/`
- [ ] 5.3 CHANGELOG: additive envelope (`comments_partial` hint + `comments_loaded`/`comments_total`); Reddit now Zyte-primary (public) with RSS fallback; note per-request cost + public-only limitation

## 6. Gate

- [ ] 6.1 `make check` green (lint + ty + tests, coverage ≥85%); `make arch` green
- [ ] 6.2 Manual: live `ask` against a real Reddit thread (keyed) returns structured scored comments + correct `comments_loaded/total`; confirm cost is as expected (httpResponseBody cheap mode)
