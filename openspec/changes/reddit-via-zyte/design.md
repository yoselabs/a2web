## Context

The prior change made Reddit reachable via RSS (keyless, degraded) and shipped env-gated paid tiers (Zyte/Firecrawl) as a generic last-resort escalation. Live exploration then established the full Reddit access map (evidence in `proposal.md`; spike scripts in `docs/history/spikes/`, ADRs 0010/0011). The load-bearing findings:

- The Reddit wall is anti-automation + IP-reputation (`snooserv` / Datadome), not auth. Cookies don't help passage; a *residential IP + a real/stealth browser* passes, a datacenter IP does not.
- **Zyte passes as a service** and its cheap `httpResponseBody` mode returns full old.reddit HTML (~436 comments) — old.reddit is server-rendered, so no browser rendering is needed.
- **old.reddit `?limit=500&sort=top` is the comment channel** (~500 flat scored comments/load); new.reddit lazy-loads and yields ~35.
- Reddit exposes `shreddit-post[comment-count]` — an authoritative total we can assert against.

This change turns those findings into the shipped Reddit path, and reserves (does not build) the self-hosted stealth-browser rung.

## Goals / Non-Goals

**Goals:**
- Reddit posts + comments actually retrievable, with a rich scored/nested sample (~500 top comments), via the existing Zyte tier.
- Any Reddit URL shape an agent sends is normalized to the channel that works (old.reddit for threads, new.reddit for listings/search).
- Never present a partial comment set as complete — emit an honest `comments_partial` signal driven by Reddit's own count oracle (ADR-0009 at comment granularity).
- A clean, availability-gated tier-arbitration ladder that keeps RSS as a free fallback and reserves a slot for a future free/private self-hosted rung — without hard-disabling anything.
- Reuse the existing `ZyteTier`; add only a fetch-mode toggle.

**Non-Goals:**
- Building the self-hosted Camoufox/zendriver browser tier or the bee/residential-egress plumbing (deferred; designed into the ladder as an Unavailable-gated rung).
- Logged-in / gated / NSFW / personalized Reddit content (needs the deferred self-hosted+cookies rung; Zyte has no session).
- Retrieving *all* comments on huge threads (infeasible + undesirable; the contract is an honest "top-N of M").
- Re-litigating the rejected access paths (Redlib, PullPush, Reddit OAuth, `.json`, cookie-replay) — closed in ADR-0010/0011.

## Decisions

### 1. URL normalization is the front door
A `normalize(url) -> (channel, canonical_url)` step maps every Reddit shape to the channel that works:
- **thread / comments** (`/comments/<id>/…`, `redd.it/<id>`, `/r/<sub>/s/<share>`, `.json`, `.rss` variants) → `https://old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top`.
- **listing / search / subreddit** → new.reddit (shreddit) canonical.
Short/share-link resolution reuses the resolver added in the prior change. `sort=top` is the default (surfaces the most-endorsed answers for a Q&A agent); a later change may let the caller override sort.

### 2. Fetch Reddit eagerly via Zyte `httpResponseBody`, not the free ladder
We *know* the free ladder (raw/jina/browser) loses on Reddit, so the Reddit handler routes straight to the paid tier instead of escalating through doomed rungs. The `ZyteTier` gains an `httpResponseBody` mode (raw proxy, base64 body) selected for old.reddit — cheaper than `browserHtml` and sufficient because old.reddit is server-rendered. `browserHtml` remains for JS-dependent targets (new.reddit listings if ever needed). Auth/billing failure still maps to the authoritative `paid_auth_error` fail-loud stop (unchanged from prior change).

### 3. Reddit-specific old.reddit HTML parser
old.reddit renders comments as flat `div.thing.comment` nodes with author, score, body, and nesting depth in the DOM — parse into structured posts + comments. This is clean HTML (no shreddit web-components), so extraction is deterministic and trafilatura-independent. Lives in the Reddit handler / a `packages/` parser, boundary-typed.

### 4. `content-expectations`: a general oracle-driven readiness contract
A per-site expectation declares an **oracle** (authoritative expected count) and a **progress** measure, and resolves to ready / partial / fail:
```
  expected()  = int(shreddit-post[comment-count])   # M, the oracle
  progress()  = parsed comment nodes                 # N
  ready   → N >= min(M, LIMIT) * TOL
  partial → N < that  → comments_partial hint + comments_loaded/total   (honest, ADR-0009)
  fail    → N == 0 while M > 0  → never-silently-miss critical hint
```
General seam, Reddit-first instance. For a browser-rendered future rung it also drives a wait/scroll action loop under a time budget (≤ 3 min, per the operator steer); for the Zyte/old.reddit path (server-rendered, one load) it is a pure post-fetch assertion. `comment-count` counts deleted/removed/deep-nested that won't all render, so `TOL` and the "top-N of M" framing are load-bearing — we report the gap, we don't chase equality.

### 5. Availability-gated tier-arbitration ladder (never hard-disable)
Each rung self-gates via the existing plugin `Unavailable` pattern; presence of config + capability decides participation:
```
  gated/logged-in content → self-hosted browser (deferred; only option, else fail loud "need login")
  public content → policy-ordered:
     1. self-hosted browser   [Unavailable until residential egress configured]  free, private
     2. Zyte / Firecrawl      [Unavailable until keyed]                           paid, robust
     3. RSS (keyless)         [always]                                            free, degraded
     4. → fail loud (never-silently-miss critical hint)
```
The order of rung 1 vs 2 is an operator policy knob (cost/privacy-first vs robustness-first). With only Zyte built now, the effective near-term ladder is `Zyte → RSS → fail loud`; rung 1 slots in later with zero ladder rewrite.

### 6. RSS demoted to fallback, not removed
The RSS handler stays as rung 3 (keyless, zero-dep). When a Zyte key is present, Reddit prefers Zyte (richer: ~436 scored/nested vs ~25 flat). Un-keyed deployments still get RSS. This preserves zero-config behavior.

## Risks / Trade-offs

- **Cost.** Every Reddit fetch now incurs Zyte per-request cost (public reads). Mitigations: `httpResponseBody` is Zyte's cheap mode; RSS remains the free fallback; the arbitration ladder lets a future free self-hosted rung take precedence.
- **Privacy.** Routing Reddit through Zyte means a third party sees every fetched Reddit URL. Documented; the deferred self-hosted rung (policy rung 1) is the private alternative. Operators who refuse third parties can set policy `self-hosted → RSS` (skip Zyte).
- **old.reddit brittleness / longevity.** Depends on old.reddit staying up and on `div.thing.comment` structure. Mitigation: a probe test that fails loudly if the parser's anchors vanish (better than silently returning junk); RSS fallback if old.reddit dies.
- **Oracle brittleness.** `shreddit-post[comment-count]` is a shreddit internal; but note the oracle is read from new.reddit while comments come from old.reddit — the expectation may need the count from the old.reddit page header instead (old.reddit shows "N comments"). Confirm the oracle source during implementation.
- **`?limit=500` ceiling.** Deep threads exceed 500; the honest contract is "top 500 of M." Getting more needs "load more" clicks (browser-only, expensive) — out of scope; the `comments_partial` hint makes the ceiling explicit.
- **Public-only.** No logged-in content until the deferred rung. Stated as a first-class limitation so agents/operators aren't surprised.
- **Dependency on the prior change.** Builds on `reddit-reachability-never-silent-miss` (Zyte tier, RSS handler, never-silently-miss envelope). It must land/stay first.
