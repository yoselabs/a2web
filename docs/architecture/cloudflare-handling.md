# Cloudflare handling — deferred work

**Status:** Backlog / not built (investigated 2026-06-09). Deferred by the
operator as a standalone problem ("we will solve cloudflare as an additional
thing"). This note captures the finding so the future pickup is turn-key.

## The finding: a CF-walled commerce page is a two-layer block

The motivating URL is a Turkish price-comparison page
(`akakce.com/.../smartmi-fan-3-...`) behind a Cloudflare **interactive
Turnstile**. a2web fails on it at **two independent layers** — fixing either
alone is insufficient.

### Layer 1 — fetch: the browser tier can't pass the challenge

`packages/browser_pool.py` launches Camoufox `headless=True`
(`AsyncCamoufox(headless=True)`, ~line 79). Empirically:

| Camoufox config | Result against akakce |
|---|---|
| `headless=True` (current product default) | stuck on *"Just a moment / Bir dakika lütfen"* 30s+, never clears |
| `headless=False` + `humanize=True` + `geoip=True` | challenge UI renders; **cleared only after a human clicked the Turnstile checkbox** |

So two sub-problems: (a) headless can't run the managed-challenge JS — a real
or virtual display is needed (`headless="virtual"` / Xvfb on Linux servers,
headful on a desktop); (b) akakce's challenge is *interactive*, so even a
display doesn't auto-pass — it needs a Turnstile interaction (click) or a
solving service. `geoip=True` helps (the operator's Istanbul IP → Turkish
locale, matching the site); it needs the `camoufox[geoip]` extra
(`maxminddb`, ~66MB GeoIP DB download on first use).

### Layer 2 — routing: a 429-turnstile page never escalates to browser

Even with the cleared DOM frozen in hand, the orchestrator never routes there.
Confirmed empirically: feeding the cleared out-of-stock DOM through the real
`fetcher.fetch` (frozen raw `429` + cleared `rendered.html` via the replay
cassette) yields `tier: jina`, `status: failed`, **`extractor called: False`**.

Why: the raw `429` is classified `Verdict.rate_limited` — a hard HTTP failure
that advances to the next `TIER_ORDER` tier (jina) **without** running the
content-based gate. `block_detector` *does* know turnstile
(`block_detector.py:134`, `EscalationSignal(next_tier="browser",
reason="turnstile")`), but it never sees the markers: the raw body is
pre-empted by the 429 status, and jina's reader strips the `cf-turnstile` /
`challenges.cloudflare.com/turnstile` markup out of its text output. So the
gate's `_decide_gate_browser_signal` rule (requires `escalation.next_tier ==
"browser"`) is never satisfied.

## What a fix would need (both layers)

1. **Routing:** when raw returns `429`/`403` with a CF/Turnstile body, inspect
   the body for block markers *before* advancing tiers, and let the planner
   escalate to browser (today the status pre-empts the content gate).
   Scope-creep risk: don't browser-escalate every 429 — gate on detected
   block markers only.
2. **Fetch:** make Camoufox headless mode configurable (settings-driven;
   default `headless="virtual"` on Linux so the deployed MCP server can run the
   challenge JS without a display), and decide a policy for *interactive*
   Turnstile (out of scope for in-house: delegate to the env-gated Firecrawl
   paid tier `tiers/paid.py`, or a Turnstile-solving service). Tradeoffs:
   virtual/headful is slower + heavier; CF is a moving arms race.

Architecturally honest default: keep the ladder (raw → jina → browser → paid)
and let the **paid tier own hard/interactive CF**, rather than building a
Turnstile solver in-house.

## Stashed specimen (for the future no-price eval)

`assets/cf-specimen-akakce-smartmi-fan-3.html` is the **cleared** page (134KB,
obtained headful + manual Turnstile click on 2026-06-09). It is a perfect
Class-C "no current price" specimen: structured data is
`AggregateOffer / availability:OutOfStock / offerCount:"0" / price:"0"`, while
the visible text carries price-*history* "TL" numbers as a fabrication trap.
When the browser path is productized, wire this as `rendered.html` on a
browser-tier eval asserting the extractor says "out of stock / no current
price / not buyable" and does **not** echo a history number as the price.

## Related

- `eval/corpus/regression/akakce-cloudflare-bot-wall/` — the deterministic
  honest-failure eval shippable today (a2web never fabricates a price for a
  page it couldn't fetch).
- ADR-0002 (real surface is ground truth) — the principle that motivates
  passing CF at all; bounded by the honest "report the wall" fallback.
- `tiers/paid.py` (Firecrawl, env-gated) — the existing escape hatch for
  bot-walled pages.
