## Why

Reddit is a2web's highest-value, most-walled source, and the prior change (`reddit-reachability-never-silent-miss`) could only reach it through **RSS** — a keyless but heavily degraded channel (~25 flat, scoreless comments; no nesting). During exploration (2026-07-03/04) we live-tested the full access space and found a path that returns the *real* content:

- **Every path a2web controls is blocked.** `curl_cffi` + logged-in cookies → Reddit's own `snooserv` "network policy" 403 on both `.json` and HTML, byte-identical with vs without cookies (the wall is anti-automation + IP-reputation, not auth). `.json` is banned even through Zyte's raw proxy (HTTP 520). Our own headless Chromium (patchright, all variants; nodriver) is fingerprint-blocked.
- **Stealth engines pass, but only from a residential IP.** Camoufox (stealth Firefox) and zendriver (stealth Chromium/CDP) pass headless *from a residential IP*; through shen's datacenter IP (Contabo `38.242.156.243`) both are blocked. Residential egress is a hard requirement — a complex, fragile subsystem to self-host.
- **Zyte (the paid tier we already built) passes as a service.** Zyte's browsers + IP pool defeat the fingerprint and IP layers at once. Its cheap `httpResponseBody` (raw, no browser rendering) mode returns **~436 comments** from `old.reddit ?limit=500` — because old.reddit is server-rendered HTML.
- **old.reddit is the comment channel.** new.reddit (shreddit) lazy-loads comments — scroll reaches only ~35 of 32,346 on huge threads. `old.reddit ?limit=500&sort=top` renders ~458–497 comments **flat, server-side, in one load**. Reddit also exposes the authoritative total via `shreddit-post[comment-count]` — an oracle we can assert completeness against.

So we can make Reddit *actually work* now — full scored/nested comment samples — by routing every Reddit URL to old.reddit and fetching via the existing Zyte tier, with no new fragile infrastructure. The self-hosted stealth-browser path stays valuable (free, private, logged-in-capable) but is deferred behind residential-egress plumbing; we reserve its slot in the tier ladder rather than build it now.

## What Changes

- **Route all Reddit URLs to old.reddit and fetch via Zyte, eagerly.** Any Reddit URL an agent sends (www/new reddit, `redd.it`, `/s/` share links, `.json`, `.rss`) is normalized to canonical `old.reddit.com/.../?limit=500&sort=top` for threads (new.reddit for listings/search), then fetched via Zyte — skipping the free ladder that provably loses on Reddit.
- **Add a `httpResponseBody` mode to the Zyte tier.** old.reddit is server-rendered, so the cheap raw mode suffices (no `browserHtml` cost). The current `ZyteTier` only does `browserHtml`.
- **Parse old.reddit flat HTML** into posts + comments (a Reddit-specific parser — clean, no shreddit web-components).
- **Introduce `content-expectations`**, a general per-site readiness contract with an oracle. Reddit is the first instance: when rendered comments `N` < claimed `M`, emit `OperatorHint(code="comments_partial", severity="info", …)` plus structured `comments_loaded`/`comments_total`, so an AI agent always knows it read "top N of M," never mistaking a sample for the whole. This is ADR-0009 (never-silently-miss) at comment granularity.
- **Establish an availability-gated tier-arbitration ladder** for Reddit (never hard-disable a tier): gated/logged-in content → self-hosted browser (deferred, only option); public → policy-ordered `[self-hosted (future, Unavailable until residential egress) → Zyte/Firecrawl (if keyed) → RSS (keyless, degraded) → fail loud]`. Self-hosted-vs-paid order is an operator policy knob (cost/privacy-first vs robustness-first).
- **Keep RSS as the keyless zero-dependency fallback** and the never-silently-miss critical hint on total failure.
- **Record the browser/IP findings** (Camoufox/zendriver pass but need residential IP; datacenter blocked; Zyte public-only) as ADR updates + backlog so the deferred self-hosted rung is not re-litigated.

**Deferred (designed into the ladder, not built here):** the self-hosted Camoufox/zendriver browser tier + bee/residential-exit egress. **Limitation:** the Zyte path is public-read only (no session) — private/NSFW/personalized content needs the future self-hosted+cookies rung.

## Capabilities

### New Capabilities
- `reddit-content-access`: normalize any Reddit URL → old.reddit (threads) / new.reddit (listings); fetch Reddit eagerly via the paid tier; parse old.reddit flat HTML into posts + comments; the availability-gated tier-arbitration ladder (Zyte-primary now, self-hosted rung reserved) with RSS fallback.
- `content-expectations`: a general per-site content-readiness contract driven by a site-provided oracle; on shortfall emits an honest partial signal (`comments_partial` hint + structured loaded/total) instead of silently returning an incomplete result.

### Modified Capabilities
- `paid-fetch-tiers`: add a `httpResponseBody` (raw) fetch mode to the Zyte tier alongside `browserHtml`, and allow eager (non-last-resort) dispatch when a handler routes a known-walled host to it.

## Impact

- **Code:** `src/a2web/handlers/reddit.py` (RSS-primary → Zyte-old.reddit-primary + normalization + old.reddit parser; RSS becomes fallback), `src/a2web/tiers/zyte.py` (httpResponseBody mode), `src/a2web/fetcher.py` / `src/a2web/actions/playbook.py` (eager paid routing + arbitration ladder), `src/a2web/models.py` (`comments_partial` hint + structured comment counts), a new `content-expectations` seam.
- **Envelope:** additive — new `comments_partial` operator hint + optional `comments_loaded`/`comments_total`. No removals.
- **Dependencies:** none new for the shipped scope (reuses the existing Zyte tier). Deferred rung would add Camoufox/zendriver + residential-egress config.
- **Cost:** Reddit fetches now incur Zyte per-request cost (public reads); documented, key-gated, with RSS as the free fallback when un-keyed.
- **Docs:** ADR-0011 update (Zyte-public works; browser+cookies works only residential; datacenter blocked); spike scripts already in `docs/history/spikes/`.
- **Depends on:** `reddit-reachability-never-silent-miss` (RSS + Zyte/Firecrawl tiers + never-silently-miss) landing first.
