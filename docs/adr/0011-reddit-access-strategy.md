# ADR-0011 — Reddit access strategy: RSS-primary, never `.json`, paid-HTML backstop

**Status:** **Accepted** (decided 2026-07-03)
**Date:** 2026-07-03
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never-silently-miss tenet), ADR-0010 (reachability evidence + rejection memory), openspec change `reddit-reachability-never-silent-miss`

> **Purpose.** ADR-0010 is the *evidence memory* — every path we tried and why we
> kept/rejected each. THIS ADR is the *operating rule*: given that evidence, how
> a2web actually fetches Reddit, stated tersely so the strategy is one lookup, not
> a re-derivation from the evidence table.

## Context

Reddit is a high-value, heavily-walled source. Over 2026-06-29 → 07-03 we tested the full access space live (ADR-0010), including a trial-key Zyte run and a logged-in-cookie replay from the operator's own machine. The results converge on a single, non-obvious operating strategy that this ADR fixes so it is not re-litigated.

**The load-bearing measured facts (all live):**

- **Every HTTP-client path is blocked, and cookies do not help.** curl_cffi (`chrome120` impersonation) against `www` HTML, `old.reddit` HTML, and `.json` all return Reddit's own `server: snooserv` *"whoa there, pardner — blocked due to a network policy"* page — **byte-identical (len 1522) with vs without logged-in cookies.** The wall is a **network-policy block on non-browser clients**, not an auth gate. Logged-in cookies (`reddit_session`/`token_v2`/`loid`) change nothing; even a real `Bearer token_v2` → `oauth.reddit.com` is blocked. No `datadome` cookie is ever minted for an HTTP client to replay.
- **`.json` is unreachable even for a commercial smart-proxy.** Zyte `httpResponseBody` (raw proxy through Zyte's IPs) on `.json` → **HTTP 520 "Website Ban."** Zyte `browserHtml` on `.json` → **timeout** (a JSON endpoint has no DOM to render).
- **The rendered HTML page IS reachable — but only through a real/commercial browser.** Zyte `browserHtml` on the search + listing **HTML** pages → **200, real content.** Our own headless browser tier (patchright/camoufox) was blocked (`block_page_detected`) — headless fingerprint flagged.
- **RSS is the only keyless path that works.** `.rss` (Atom) for search/listing/thread returns 200 from a datacenter/remote IP (ADR-0010), because it is served by a different, non-API-gated channel.

## Decision

a2web works with Reddit under these rules:

1. **RSS is primary and keyless.** The Reddit handler projects `search` / `listing` / `thread` URL shapes to their `.rss` (Atom) equivalents and parses those. This is the default and the only free path. (`handlers/reddit.py`, shipped in this change.)

2. **Never touch `.json` / `oauth` for Reddit content.** Proven unreachable for every automated client we control (HTTP client *and* Zyte's proxy), and cookies/Bearer do not unlock it. The handler MUST NOT rewrite to `.json`, and no "logged-in `.json`" or "OAuth API" tier may be added on the assumption that cookies would pass — that assumption is measured-false. (Re-open only via the trigger below.)

3. **Cookies are not a Reddit unlock.** `cookie_jar` mirroring is a no-op against the `snooserv` wall (byte-identical). Do not build a Reddit path whose premise is "replay the user's session cookies through an HTTP client." Cookies only ever add *logged-in content on top of* a channel that already passes the wall (i.e. a real browser), never passage itself.

4. **Paid backstop reaches Reddit via the rendered HTML page, never `.json`.** When a Reddit shape the handler does not claim reaches the paid tier (or RSS fails), Zyte's `browserHtml` on the HTML URL is the escalation. Its full-page markdown is SPA-noisy, so `_escalate_paid` runs the trafilatura extraction ladder on the HTML (mirrors `_escalate_browser`) before installing. Paid is out-of-band, last-resort, capped 1/fetch (ADR-0010, `_deps.md`).

5. **Degradation is explicit, never silent (ADR-0009).** RSS output is a **flat, scoreless, recent-ordered sample** — surfaced as such, never as a complete/ranked comment set. On terminal exhaustion the fetch sets `retrieval_incomplete` and emits the critical `try_user_browser` hint eagerly (Reddit) — the full tier ladder is proven to lose, so we do not burn a doomed browser dispatch.

## Consequences

- **We accept a degraded Reddit read.** No comment scores, no nesting, no `more`-stub expansion, a bounded sample. That is the price of the only keyless channel; the envelope says so out loud.
- **Clean structured Reddit JSON is off the table** for a2web's automated egress. Anything needing full ranked comment trees must go through a real logged-in browser (see trigger).
- **The paid tier helps Reddit only marginally** — it fires for unclaimed shapes / RSS failure and returns extracted HTML, not clean JSON. Its real value is walled *non-Reddit* pages.

## POC — the winning recipe (validated 2026-07-03)

Spiked patchright (a2web's Chromium backend) against Reddit locally, varying two axes. Only one cell passes:

| | no cookies | logged-in cookies (via `cookie_jar`) |
|---|---|---|
| **headless** | 🛑 "blocked by network security" | 🛑 403 `snooserv` |
| **headful** (`headless=False`) | 🛑 "blocked by network security" | ✅ **PASS** |

The passing cell (**headful + cookies + operator's residential IP**) returned full content: hot listing (6 posts), the *original failing* search URL, and a comment thread with **100 comments rendered** (real nesting + scores in the DOM) — strictly richer than RSS or `.json`. Remove any one ingredient and it blocks. Script: `docs/history/spikes/browser_headful_poc.py`.

**This refines rule 3:** cookies are not an unlock *by themselves* (no-op for an HTTP client OR a headless browser), but they ARE the decisive ingredient *in a headful browser*. The full unlock is the **triple**: headful + session cookies + non-flagged IP.

**Consequence for the build:** the productized path is a **headful** browser a2web drives with the operator's session — NOT headless, NOT cookie-replay-through-HTTP. On a server this means headful-under-virtual-display (Xvfb / neko / Kasm) + residential egress (or run a2web on the operator's own node). Locally it works today: headful patchright + `cookie_jar`. Tracked as a new change (`reddit-browser-auth`, TBD) — out of scope for `reddit-reachability-never-silent-miss`.

## Re-evaluation triggers

- **Remote productization of the headful path.** The POC proves the recipe on the operator's local machine/IP. Productizing for a remote a2web needs (a) headful-under-virtual-display in a container and (b) a residential egress or home-node. Spike as `reddit-browser-auth`.
- **Cookie rotation / session longevity.** The POC mirrored live Chrome cookies; a dedicated persistent authenticated profile (sign-in-once) is the robust variant. Evaluate in the same change.
- **Re-run the HTTP probes from a known-clean residential IP.** The `snooserv` block is IP-sensitive; if `.json` + Bearer passes from a clean IP, rule 2's HTTP path could reopen. Probe scripts: `docs/history/spikes/reddit_json_cookie_spike.py`.
