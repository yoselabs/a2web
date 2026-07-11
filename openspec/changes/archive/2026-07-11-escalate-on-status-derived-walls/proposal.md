## Why

a2web's escalation ladder (`EscalateBrowser` → archive → `EscalatePaid` → loud fail) only engages for a 2xx body the content gate (`block_detector`) could read. A tier failure that never yielded a readable body — a bare **403, 5xx, timeout, connection-reset, or uncorroborated 404** — produces a verdict `decide_next` has **no rule for**, so it returns `Continue()`, the next free tier is tried, and when the free waterfall (`site_handler → raw → jina`) is exhausted the loop simply **ends**. The rich escalation ladder is never consulted. That is the silent-skip gap: a walled/failed URL is reported as unfetchable without browser **and** paid ever having been tried — a latent violation of the first-class ADR-0009 invariant (*never tolerate an unfetched URL*). A WAF that fakes a 403/404/500 to non-browser clients — a real, documented anti-scraping technique — is trusted at face value today.

Step 1 (`unify-escalation-executor`, shipped) made the ladder **reachable** from the tier-walk via the single `_dispatch_action`. This change adds the planner rules that actually **route** transport/status failures into it — the product payoff that closes the gap.

## What Changes

- **New `PlannerRule`s that escalate ambiguous transport/status failures to `EscalateBrowser`.** Each reads the last tier observation's `verdict` + `status_code` + `authoritative` (all already on the decision log — no verdict-splitting in the tiers is needed). The existing ladder then carries a still-walled result to archive (where applicable) → `EscalatePaid` → the loud never-silently-miss terminal.
- **Ambiguous → escalate:** 403 (treated as anti-bot by default), 5xx, other 4xx, `timeout`, connection-reset / TLS drop (status-0 `connection_error` that is not DNS), **uncorroborated** 404 (`not_found` without the `authoritative` flag), and 429 after retry exhaustion (generalized from today's search/listing-only behavior).
- **Terminal → do NOT escalate (three carve-outs, on purpose):** (1) genuine DNS NXDOMAIN (identified via Step 0's `dns_error` verdict); (2) an **authoritative** 404 (a site handler that models the site's real "gone" semantics — the existing `authoritative` flag); (3) a genuinely-thin 2xx page with no anti-bot fingerprint (already handled by the gate — unchanged).
- **Intended behavior change (unlike Step 1):** a 403/5xx/timeout/uncorroborated-404 that today ends as a bare failure will now try browser + paid first, then fall to the same loud ADR-0009 terminal if still walled. The output-preservation bar does **not** apply here — widening escalation is the whole point.
- **Cost discipline preserved:** the new rules return `EscalateBrowser` (cheap self-hosted rung, fast→robust, cap 2), never `EscalatePaid` directly — free browser before paid egress stays baked into rule priority. New rules sit at **LOW** priority so any more-specific content/gate signal still wins; they are the catch-all floor.

**Dependency:** Step 0 (shelf `http-fetch` `dns_error` verdict) is a **hard prerequisite** for the clean DNS carve-out — until a2web can see a `dns_error`, a status-0 `connection_error` cannot be distinguished as NXDOMAIN vs. a network block. The design plans the correct behavior with Step 0 assumed; the interim fallback (escalate all status-0 `connection_error`, accepting one wasted capped attempt on a genuinely-dead domain) is documented if Step 0 slips.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `cascade-decision-log`: new `PlannerRule`s (transport/status escalation) added to `_RULES`, reading `status_code` / `authoritative` from the tier observation. The "Escalation is decided by a pure planner" contract gains rules for the transport-failure population; the existing rule-identity + test-pair requirement applies to each.
- `retrieval-completeness`: the "An unfetched URL is never mistakable for success" floor is extended so it structurally covers **transport/status** walls (403/5xx/timeout/uncorroborated-404/connection-reset), not only the content-gated `paywall`/`block_page_detected`/`anti_bot` verdicts — the ladder now runs for these before the loud terminal fires.

## Impact

- `src/a2web/actions/playbook.py` — the primary surface: new rule callables + `_RULES` entries at LOW priority, reading `last.status_code` / `last.verdict` / `last.authoritative`. `decide_next` remains pure/total; rule-name-uniqueness and per-rule test pairs preserved.
- `src/a2web/fetcher.py` — verify `status_code` is present on every failure observation the rules read (the main tier-failure observe passes it; `proxy_unavailable` defaults to 0, which is correct). If Step 0 has landed, map `FetchVerdict.dns_error` → a terminal `Verdict` at the tier boundary (`tiers/raw.py::_TRANSPORT_TO_DOMAIN`) so the DNS carve-out rule can key on it.
- **Behavior change:** transport/status failures now escalate. Existing tests asserting "transport failure X ends immediately" must be updated to the new escalate-then-(maybe)-fail behavior — legitimate expectation changes, not contrived-fixture edits. New tests assert each ambiguous verdict escalates and each of the three terminal leaves does not.
- Caps unchanged (browser 2, paid 1); the new rules respect `browser_dispatches < 2` so they cannot spin; termination unchanged; the loud ADR-0009 terminal (status failed + retrieval_incomplete + diagnostics + narrative + critical `try_user_browser` hint) is the floor these rules feed, not replace.
- No wire/envelope change, no tool-signature change, no new dependency.

Not in scope: the executor unification (Step 1, done); the shelf `dns_error` split (Step 0, separate prerequisite); `single-source-escalation-policy` (Finding 2, separate); the archive-staleness hint (Step 3, separate).
