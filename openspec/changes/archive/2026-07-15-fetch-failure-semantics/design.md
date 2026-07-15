# Design — fetch-failure-semantics

## Context

a2web returns a structured envelope to a **calling AI agent**. The envelope's failure signals (`status`, `verdict`, `operator_hints[].severity`, `narrative`, `retrieval_incomplete`) are not decoration — a CRITICAL hint is an *imperative injected into the caller's context*, and agents act on it. So the cost of a miscalibrated failure signal is a wrong downstream action (e.g. burning a browser session on a URL that does not exist), not just noise.

This change was pressure-tested against an independent senior-architect review. The review reframed the incident (below) and its corrections are folded in.

## The incident, precisely

A dead search URL (genuine HTTP 404) produced `length_floor` + CRITICAL `try_user_browser`. Two independent bugs, chained:

- **Bug 1 — a tier lies.** `jina` wraps an upstream 404 as its own HTTP 200 (`_verdict_for_status(200) == ok`), so it *wins the tier loop* and installs a stub body. `browser` renders the 404 page and also reports `ok` (bytes returned), with the 404 only in a diagnostic. The decision log now contains false `ok` observations.
- **Bug 2 — the classifier reads a projection.** `_is_genuine_gone()` branches on `resolved_verdict()` (`length_floor`), so the `raw:404` (and browser 404) observations are structurally unreachable. Fixing jina alone does **not** fix this — the predicate must read the *log*.

## Decisions

### D1 — Un-wrap upstream status at the TIER, not the gate

**Decision:** `jina` decodes its own reader wrapper and reports the real upstream status/verdict on `TierResult`; the gate's jina-stub regex is deleted.

**Why:** the block-detector's own doctrine is "the detector emits typed evidence about *content*; the planner acts." A jina wrapper stub is not content — it is jina's transport protocol encoded in a body. Decoding a tier's own protocol is tier work, by the same logic that HTTP-status parsing is tier work. The `tier == "jina"` guard in `evaluate()` is the confession that the logic was mis-layered. Generalizing beyond jina: any future reader-style tier gets truthful evidence for free.

**Generalize the pattern, not the enum.** Capture `Target URL returned error (\d{3})` and route through the existing `_verdict_for_status`, rather than adding a `404` arm. Enumerate-by-status is exactly the anti-pattern that let `40[13]` miss 404.

**Consciously preserve routing (not a silent drift):** today a wrapped 401/403 is promoted to `Verdict.paywall` specifically so `gate_paywall_or_block_archive` fires (Wayback can recover blocked/paywalled content; jina already tried server-side, so browser-first is weaker here). Moving unwrap to the tier would otherwise make 403 → `connection_error` → browser-first. We **keep** the paywall mapping inside the jina unwrap so routing is behaviour-neutral except the 404 fix.

**Guard against false positives:** keep the body-length ceiling so a long article that *quotes* "Target URL returned error 404" cannot be misread as a wrapper stub.

### D2 — Bug 1 is systemic: the `browser` tier lies too

The corroboration model (D4) needs "the browser also returned 404" to be an *observation*, not a buried diagnostic. Today the browser tier reports `ok` for a rendered error page. So the tier-truthfulness contract is **general**: a tier that retrieves an error page surfaces the upstream status. This is the linchpin — without it, `classify_terminal` would count phantom corroboration.

### D3 — One pure `classify_terminal`, sibling to the playbook

**Decision:** replace `_is_genuine_gone` + `_prescribe_browser_on_wall` with `classify_terminal(observations, resolved_verdict) -> TerminalOutcome`, a closed enum: `wall | gone_confirmed | gone_unverified | operator_error | unreachable`. Pure, total, log-reading, in `actions/terminal.py` next to `playbook.py`.

**Why not a bigger "retrieval outcome classifier"?** The forward-looking half already exists and is good: `playbook.decide_next(log) -> Action`. Building a second omnibus classifier would create a rival source of truth to keep consistent. The *missing* half is purely the terminal story (log → narrative/hint/severity), today split across two inverse whitelist functions. Consolidating exactly those two — no more — is the 20% that removes 80% of the smell. This is a deliberate scope wall against over-consolidation.

### D4 — `not_found` semantics keyed on CORROBORATION, not on the 404's source

The user's instinct (a third, middle not-found state) is correct; the *mechanism* is corroboration, because the cascade **already** browser-checks an uncorroborated 404 (`_decide_uncorroborated_404_escalate`). The soft-404 is therefore *tested*, not hypothesized. `classify_terminal` reads the outcome of that test:

| Observed | TerminalOutcome | Wire |
|---|---|---|
| handler-authoritative not_found | `gone_confirmed` (authoritative) | silent, `status: failed`, no hint, not incomplete |
| HTTP 404 + browser also 404 | `gone_confirmed` (corroborated) | INFO "not found — likely dead URL, confirmed by a rendered browser"; no `try_user_browser`; no soft-404 caveat |
| HTTP 404 + check couldn't run / browser saw something else | `gone_unverified` | WARNING "likely a dead URL; small chance a bot-defense soft-404 masks it; try your own browser if you truly need it" |
| content wall (block/anti_bot/paywall/blank) | `wall` | CRITICAL `try_user_browser` (unchanged) |
| dns_error / content_type_mismatch | `unreachable` | as today (silent/no-wall) |
| paid_auth_error | `operator_error` | dedicated hint (unchanged) |

**Anti-cry-wolf is structural:** severity encodes confidence, confidence comes from corroboration count. `gone_unverified` (the only caveat-bearing 404) is rare (browser pool down / budget spent), so its WARNING keeps signal. The calling agent can learn a stable contract: `info` = verified fact, `warning` = we couldn't finish checking, `critical` = we tried everything and hit a wall.

**Optional tuning (in scope, one line):** an uncorroborated 404 shares the `< 2` browser cap and can burn *both* the fast and robust rungs. Under "effort ∝ existence prior," a 404 deserves at most one rung. Cap it at one.

### D5 — Incoming reader-prefix normalization

If a caller passes `https://r.jina.ai/<real-url>`, `fetch()` strips the prefix and fetches `<real-url>` with the full ladder. A pre-wrapped URL otherwise pins a2web to jina alone (it treats `r.jina.ai` as the origin) with no raw/browser/paid fallback — the opposite of resilience. The agent should never need to pre-wrap; if it does (unaware a2web owns jina internally), a2web must reclaim control, not inherit a dead end. Sibling to `rewrite_captcha_host`; surfaces the real target as `requested_url` so the wire stays honest.

### D6 — Taxonomies relate by a tested invariant; they do NOT collapse

`Verdict` (deterministic transport/gate outcome, 15-way), `Obstacle` (LLM-emitted content read, Literal-4 *because* LLMs are unreliable at wide classification — an independent second witness), and `OperatorHint`+`severity` (an imperative) are different layers, producers, and reliabilities. Collapsing them breaks the MCP contract for negative value. The genuine gap is an *undeclared consistency relation*: the incident was `verdict=length_floor` + `hint=try_user_browser` on `not_found` evidence — an incoherent combination. Declare the coherence table (which hint codes are legal per `TerminalOutcome`, which obstacles cohere with which verdicts) and assert it in `tests/architecture/`. (`OperatorHint.code` being open-string is the weakest of the three; a closed Literal is a future contract touch, not now.)

## Alternatives considered

- **Add a 404 branch to the gate regex** (the original quick fix) — rejected: patches Bug 1's symptom, leaves Bug 2, and perpetuates enumerate-by-status.
- **Caveat every 404** (the user's first mechanism) — rejected: caveats where we already check; trains agents to ignore caveats. Replaced by corroboration-keying.
- **One omnibus outcome classifier** — rejected: rival source of truth to the log + playbook; over-consolidation.
- **Collapse `Verdict`/`Obstacle`** — rejected: couples the LLM prompt contract to the pipeline enum, degrades extraction, breaks the wire.

## Out of scope / follow-ups

- The **200-soft-404** case (HTTP 200 + "no results" body, zero status evidence) is captured in the corpus and its `length_floor`-with-no-wall-fingerprint narrative is hedged, but a positive fix is deferred (needs a content-level "empty result set" signal, not a transport signal).
- A closed-Literal `OperatorHint.code` — a future contract touch.
- Short-TTL **negative cache** for a `gone_confirmed` URL (a verified fact that cost three tier dispatches) — optional, and only ever safe for `gone_confirmed`, never `gone_unverified`.
