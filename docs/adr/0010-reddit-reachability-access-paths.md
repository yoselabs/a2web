# ADR-0010 — Reddit reachability: access-path decisions & rejection memory

**Status:** **Accepted** (decided 2026-07-03)
**Date:** 2026-06-29 → 2026-07-03 (exploration) · **Decided:** 2026-07-03
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never-silently-miss tenet), openspec change `reddit-reachability-never-silent-miss`, Constitution Articles III (adopt-before-build) + VIII (dependency memory)

> **Purpose.** This ADR is the durable memory of *every* Reddit access path we
> tried, adopted, rejected, or deferred, with citable reasons and re-evaluation
> triggers. Per Constitution Article VIII it exists so none of these get
> re-litigated as a "fresh idea" (the hishel anti-pattern). Do not delete a
> rejection because it looks obvious later — the evidence is the point.

## Context

Reddit is a high-value source for a2web, which is **remote-first** (runs on a server to offload retrieval from the caller). As of mid-2026, every anonymous/automated/remote-safe path into Reddit is walled by Datadome. We tested the full space live over 2026-06-29 → 07-03.

## Evidence trail (all tested live)

| Path | Result | Verdict |
|---|---|---|
| `www.reddit.com/.json` (curl) | 403, ~190KB Datadome challenge HTML | walled |
| `.json` via curl_cffi `impersonate=chrome` | 403 | TLS impersonation insufficient |
| `.json` + logged-in Chrome cookies (curl_cffi `chrome120`) | **403 — Reddit's own "whoa there, pardner" `server: snooserv` page, NOT Datadome.** Cookies sent + present (reddit_session/token_v2/loid), zero effect (byte-identical to no-cookie). Even `oauth.reddit.com` + real `Bearer token_v2` → same 403. | walled by IP/network-policy, not solvable by cookie replay (spike 2026-07-03) |
| `www`/`old.reddit` **HTML** page + logged-in cookies (curl_cffi `chrome120`) | **403 `snooserv`, byte-identical (len 1522) with vs without cookies.** Confirms the wall is not `.json`-specific and not auth — every HTTP-client path to Reddit is network-policy-blocked. | walled; cookies irrelevant to passage (spike 2026-07-03) |
| jina reader (`r.jina.ai`) | 403 — *"log in to your Reddit account or use your developer token"* | walled; Reddit names the only 2 endorsed paths |
| Patchright (current browser tier) | HTTP 200 but body = *"blocked by network security"* | `block_page_detected` |
| Camoufox (prior browser tier) | `block_page_detected` (14s) | walled |
| proxy-through-Shen (Contabo datacenter egress) | 403 | datacenter ASN + JS challenge |
| Claude Code native `WebFetch` (www + old.reddit) | domain-denylisted, refuses before network | unavailable |
| Claude Code native `WebSearch` | zero reddit.com URLs; secondhand summaries only | Reddit not in that index |
| **Reddit `.rss` (Atom)** | **200** — search: 25 entries; thread: post + comment bodies; works via datacenter proxy; 429 on bursts | **ADOPTED** |
| PullPush.io | 200, scored full-text comment search — but newest record ~May 2025 (ingest stalled ~14 months) | deferred |
| Public Redlib instances | 403 / 429 / anti-bot challenge / "shut down" redirect | rejected |

**Two structural facts:** (1) Reddit's wall is a **JS challenge** (Datadome), so an HTTP client — however good its TLS or IP — cannot solve it; (2) Reddit's own error text names the only endorsed paths: **log in** or **developer token**. Everything that works is either a different keyless channel (RSS) or authenticated.

## Decisions

### ADOPTED — RSS (primary, keyless, remote-safe)
Reddit gates `.json` but leaves `.rss` open (feed readers need it). Rewrite `search`/`listing(top,new)`/`thread`/`user` → `.rss`; parse Atom. **Limits (surfaced, never hidden):** flat (no reply tree), ~25 recent entries (not top-ranked), no scores, tight per-IP rate limit → backoff + `http_cache`. `hot` does not project (algorithmic).

### ADOPTED — Zyte + Firecrawl paid tiers (env-gated backstop)
Zyte (`$0.13/1K`, pay-as-you-go, the Scrapy company — most reputable) and Firecrawl (`$16/mo`, AI-native, already partially wired) as `_manifests/tiers/` plugins, keyed by `A2WEB_ZYTE_KEY` / `A2WEB_FIRECRAWL_KEY`. Graceful no-op un-keyed (manifest returns `Unavailable`, tier never registers); **fail loud on bad key — never silent downgrade** (ADR-0009): a `paid_auth_error` is authoritative (rank 12) and STOPs escalation, never falling through to a sibling paid tier. Dispatched out-of-band (`priority=-1`) only after the free/proxied ladder hits a wall — never speculative. Per-tier dep decisions recorded in `src/a2web/tiers/_deps.md`.

**VALIDATED live with a trial key (task 4.9, 2026-07-03):** Zyte `browserHtml` **passes** Reddit's wall — the search + listing **HTML** pages returned real content (200). BUT (a) Zyte `httpResponseBody` (raw proxy) on the `.json` API endpoint → **HTTP 520 "Website Ban"** (banned even for Zyte's proxy — the `.json` IP-ban beats a commercial smart-proxy headlessly); (b) `browserHtml` on `.json` **times out** (no DOM to render). So the paid tier reaches Reddit only via the **rendered HTML page**, never the clean `.json`, and the browserHtml→markdown is SPA-noisy → `_escalate_paid` now runs the trafilatura extraction ladder on the HTML (mirrors `_escalate_browser`) to clean it. Net: Zyte is a validated backstop for walled HTML pages generally; for Reddit specifically the RSS tier remains primary (paid only fires for unclaimed shapes / RSS failure).

### ADOPTED — critical browser-escalation hint
On terminal `paywall`/`block_page_detected`/`anti_bot`: `retrieval_incomplete` + `OperatorHint(code="try_user_browser", severity="critical")`, imperative + capability-generic. **Eager for Reddit** (handler emits on RSS/`.json` exhaustion — the full ladder is proven to lose, so skip the doomed 14s browser tier); **late generically** (other hosts' jina/archive/browser tiers have real hit rates). This is the only Claude-Code-native path that reaches Reddit at all: `WebFetch` is denylisted, `WebSearch` lacks Reddit — only the caller's real logged-in browser passes.

## Rejected / deferred (with reasons + re-evaluation triggers)

### REJECTED — Redlib (self-hosted or public)
Redlib works by **OAuth credential spoofing** (mimics the official iOS/Android app, refreshes a token every 24h). Public instances are dying (tested: 403 / 429 / anti-bot `.gandalf/check` / "shut down" redirect) because thousands share one IP+identity against Reddit's ~100-req/10-min cap. Self-hosting works but is **"OAuth in a costume"** — a fragile spoofing service to babysit, same rate cap as your own OAuth, community-maintained cat-and-mouse (Reddit broke it June 2025).
**Re-eval trigger:** if a2web ever needs full ranked comment trees keyless AND Redlib gains stable maintenance + a non-spoofing auth path.

### DEFERRED — PullPush.io (Pushshift successor)
Free cross-Reddit **scored** full-text comment/submission search, structurally projectable (submission `ids=`, comments `link_id=`, batch via `ids=`). But newest record is ~May 2025 — **ingest stalled ~14 months** (identical clustered `created_utc` on newest rows). Automatic use = silent staleness = violates ADR-0009. Historical-only.
**Re-eval trigger:** PullPush resumes near-real-time ingest (test: newest-record lag < 48h) — then viable as an explicit, clearly-labeled *historical* tier, or for the future cloud/home node-mode idea.

### DEFERRED — Reddit OAuth API
Works: 100 QPM free (non-commercial), `oauth.reddit.com` + Bearer, full data. But the Nov-2025 "Responsible Builder Policy" requires **pre-approval for every app** (even hobby), and it's a real credential. Deferred in favor of keyless RSS + paid backstop.
**Re-eval trigger:** RSS + paid prove insufficient for the comment-depth need AND the approval gate is acceptable. Would return as an env-gated depth tier, graceful when un-keyed.

### REJECTED — proxy-through-Shen (the homelab proxy hub)
Shen's reachable exits egress a Contabo **datacenter** IP (`38.242.156.243`). Tested: `.rss` passes but `.json` still 403s — datacenter ASN + the JS challenge an HTTP client can't solve. Proxies fix only IP reputation (one layer); they don't solve the challenge layer. Fine for other hosts blocked purely on IP; useless for Reddit `.json`.
**Re-eval trigger:** a genuine residential exit on Shen AND confirmation that residential-IP `.json` is served without challenge.

### REJECTED (for remote) — Chrome-inside-a2web, rdt-cli, OpenCLI, Agent-Reach login-CLIs
All are **local-desktop, browser-cookie architectures.** Investigated the 23k-star Agent-Reach and its backends:
- **rdt-cli** — under the hood is `.json` + `browser-cookie3` (reads local browser cookies). That is *exactly* `cookie_jar` + a2web's existing handler. No anti-Datadome magic; its "reads work anonymously" claim is the pre-Datadome world. Extra surface = CLI ergonomics + **write actions** (upvote/downvote/save/subscribe/comment) — **out of a2web's read-only scope** (mutating the user's account, account-risk, needs real auth). Considered and **declined**: nothing there a2web lacks on the read side.
- **OpenCLI / Agent-Reach** — ride your *logged-in local Chrome* via a Browser Bridge extension + daemon. Fundamentally local; a2web is remote → no local browser to read cookies from.
- **Chrome-inside-a2web** — on a remote server it isn't logged in, and mirrored session cookies replayed from a datacenter IP get flagged (Reddit binds sessions to IP/fingerprint). Agent-Reach *confirms* this by requiring a desktop session.
**Re-eval trigger:** the companion-browser-container track below (a legitimate remote way to hold a logged-in session).

## Future directions (documented, NOT built here)

- **Companion browser container** (adopt-before-build per Article III — neko / `linuxserver/chromium` / Kasm): user signs into Reddit once via a remote browser UI; a2web drives the *live browser session* (full JS + fingerprint) — **not** a cookie mirror, which the spike below proved insufficient. Security-sensitive (a browser holding logins) and datacenter-egress (residential proxy helps). **Crux revised by the 2026-07-03 spike:** the blocker is not cookie-solvable — a real browser session is required. rdt-cli's "reads work with cookies" claim is the *pre-network-policy* world and does not reproduce here.
- **yt-dlp / YouTube transcription tier** — no login, remote-safe; steal from Agent-Reach (Article III adoption research).
- **Agent-Reach patterns to steal** — ordered multi-backend with auto-reorder ("first working becomes active"; auto-drop a blocked backend), and a `doctor` coverage-gap surface (directly serves ADR-0009).

## The load-bearing question — ANSWERED (spike, 2026-07-03)

**Does `.json` + logged-in cookies pass?** **No.** Tested live: read the user's logged-in Chrome reddit.com cookies (`reddit_session`, `token_v2`, `loid` all present) and replayed them through curl_cffi `chrome120` (a2web's exact raw-tier impersonation) against listing + search `.json`. Result: **403 with cookies is byte-identical to 403 without** (`len=1522`). Adding browser-like headers (Accept/Referer/Accept-Language) did not change it. Calling `oauth.reddit.com` with a real `Bearer token_v2` (the web app's actual auth) also 403'd.

**Two corrections to this ADR's earlier assumptions:**
1. **The `.json` wall here is NOT Datadome.** The block page is Reddit's own *"whoa there, pardner! Your request has been blocked due to a network policy"* (`server: snooserv`, redditstatic header) — an IP/network-policy block on non-browser API clients, not a JS challenge. No `datadome` cookie was even present in the jar.
2. **Cookie replay is a dead end.** The legacy `.json` endpoint isn't cookie-authenticated, so mirroring browser cookies cannot unlock it; and the authenticated `oauth` path is IP-walled from this egress. This kills the "`cookie_jar` → logged-in `.json`" path definitively.

**Caveat:** run from the operator's current egress IP, which may itself be flagged (VPN/datacenter) — the snooserv block is IP-sensitive, so the *reason* could be partly IP-specific. But "cookies/Bearer/headers make no difference" holds regardless of IP.

**Net effect:** RSS (shipped) remains the only keyless win. The companion-browser-container track's value proposition shifts from *cookie mirror* to *drive a live logged-in browser session* — a heavier lift, re-scoped in "Future directions" above. **Re-eval trigger:** re-run this spike from a known-clean residential IP; if `.json` + Bearer passes there, the block is purely IP-reputation and a residential-proxy + OAuth path reopens.

Spike script preserved at `docs/history/spikes/reddit_json_cookie_spike.py`.
