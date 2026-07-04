> Sequencing: group 1 (Zyte raw mode) and group 2 (URL normalization + old.reddit parser)
> are independent and can proceed in parallel; group 3 (eager routing + ladder) wires them
> together; group 4 (content-expectations) layers the honest-partial contract on top.
> Depends on `reddit-reachability-never-silent-miss` having landed (Zyte tier + RSS handler + never-silently-miss envelope).

## 1. Zyte raw fetch mode (paid-fetch-tiers)

- [x] 1.1 Add a `mode` toggle to `ZyteTier` (`browserHtml` | `httpResponseBody`); in raw mode POST `{"url", "httpResponseBody": true}`, base64-decode the body, return as `TierResult` (content_type from response headers)
- [x] 1.2 Keep the 401/402/403 → authoritative `paid_auth_error` fail-loud mapping identical in both modes; keep timeout/connection mapping
- [x] 1.3 Allow the mode to be selected per-dispatch (handler/orchestrator picks raw for old.reddit); default stays `browserHtml`
- [x] 1.4 Tests: raw mode decodes body + returns HTML; bad key → `paid_auth_error` STOP in raw mode; mode selection honored

## 2. Reddit URL normalization + old.reddit parser (reddit-content-access)

- [x] 2.1 `normalize(url) -> (channel, canonical_url)`: thread/comments (www/old/np/new hosts, `.json`/`.rss` variants, focused permalinks) → `old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top`; listing/search/subreddit → new-reddit canonical. Never emit `.json`. (`redd.it/<id>` short links resolved by the handler *before* normalize, as today.)
- [x] 2.2 old.reddit flat-HTML parser: `div.thing.comment` → author, score, body, nesting depth; the post header → title/author/score. In `handlers/_reddit_html.py` (pure, no settings), selectolax CSS selectors, no shreddit web-components, trafilatura-independent
- [x] 2.3 Read the comment-total oracle — **resolved: read off the old.reddit post's `a.comments` "N comments" bylink** (the page we actually fetch), not new-reddit `shreddit-post[comment-count]`. Needed by group 4
- [x] 2.4 Tests: normalization table for every input shape; parser on a captured old.reddit fixture yields structured scored/nested comments; oracle extracted

## 3. Eager Reddit routing + arbitration ladder (reddit-content-access + paid-fetch-tiers)

- [x] 3.1 Reddit handler: routes threads eagerly to Zyte raw (old.reddit `?limit=500`) when keyed, bypassing the free ladder; falls back to RSS when un-keyed / on transient Zyte miss. Never `.json`
- [x] 3.2 Eager dispatch lives in the **handler** (calls `ZyteTier(mode="httpResponseBody")` directly + parses), mirroring the existing `_fetch_old_reddit` seam — not a new playbook action. The last-resort `EscalatePaid` planner path is unchanged. (Cleaner than a playbook signal; the design allowed either.)
- [x] 3.3 Availability-gated: `_zyte_reddit_enabled(state)` gates on keyed Zyte + `robustness` policy. Added the `reddit_tier_policy` knob (`robustness` default = `Zyte → RSS`; `privacy` = RSS-only, no third party). The self-hosted rung + gated/logged-in-content path are **deferred** (design §5; BACKLOG 5.2) — near-term effective ladder is `Zyte → RSS → fail loud`
- [x] 3.4 RSS handler kept as the keyless fallback rung; the never-silently-miss critical hint on total failure is unchanged
- [x] 3.5 Tests: keyed → Zyte raw + old.reddit (not the free ladder); un-keyed / `privacy` → skip Zyte; bad key → fail loud; transient Zyte miss → RSS fallback. (Gated-content-fail-loud deferred with the self-hosted rung.)

## 4. content-expectations honest-partial contract (content-expectations)

- [x] 4.1 `content_expectations.assess(loaded, total) → ready | partial | fail` — pure general seam (measures completeness against the full oracle, tolerance absorbs trivial deleted-comment gaps); Reddit-first instance wired to the parsed comment count vs the `a.comments` oracle
- [x] 4.2 Reddit thread: on `partial`, emits `OperatorHint(code="comments_partial", severity="info", …)` + `comments_loaded`/`comments_total` on both `FetchResponse` and `AskResponse` (additive; omit-when-empty). Zero-vs-positive-oracle → returns None → RSS fallback (which fires its own never-silently-miss critical hint if it too fails)
- [x] 4.3 Bounded satisfaction effort: the Zyte/old.reddit path is a pure post-fetch assertion (one load). The ≤3-min action-loop budget for a scrolling browser rung is documented in the seam module + design, not built
- [x] 4.4 Tests: deep thread → `comments_loaded/comments_total` + `comments_partial` hint (unit + end-to-end via `fetch()`); small thread within tolerance → `ready`, no hint; zero-vs-positive → `fail`

## 5. Docs + decision records

- [x] 5.1 Updated ADR-0011 with a superseding `reddit-via-zyte` section: Zyte-public validated (httpResponseBody on old.reddit); browser+cookies works but ONLY from residential IP; datacenter (shen/Contabo) blocked; the arbitration ladder + Zyte-primary/self-hosted-deferred decision
- [x] 5.2 BACKLOG: the deferred self-hosted Camoufox/zendriver browser tier + residential-egress rung (Unavailable-gated rung 1) + the content-expectations action loop. References the spike scripts in `docs/history/spikes/`
- [x] 5.3 CHANGELOG `[Unreleased]`: additive envelope (`comments_partial` hint + `comments_loaded`/`comments_total`); Reddit now Zyte-primary (public) with RSS fallback; `reddit_tier_policy` knob; per-request cost + public-only limitation

## 6. Gate

- [x] 6.1 `make check` green (lint + ty + tests, coverage ≥85% → 89.34%); `make arch` green; golden contracts re-blessed additive-only
- [x] 6.2 Live-validated (2026-07-04): keyed fetch of a real r/AskReddit thread (7,899 comments) returned `comments_loaded=489`, `comments_total=7899`, scored + 5-deep-nested comments, `comments_partial` hint, tier `site_handler:reddit`, normalized old.reddit `?limit=500&sort=top`. RSS was itself IP-blocked mid-run — confirming the Zyte path is load-bearing. Key handled env-only.
