## Context

`decide_next(log, url, caps) -> Action` (`actions/playbook.py`) is a pure ruleset over the observation log. Today its rules react to *content-gate* signals (`gate_outcome` observations carrying anti-bot / paywall / block evidence) and a couple of URL-pattern / Reddit heuristics. There is **no rule** for a bare transport/status failure. Meanwhile Step 1 made the single `_dispatch_action` executor dispatch the full `Action` union from the tier-walk too — so a rule that returns `EscalateBrowser` from a tier-failure observation would now actually fire and reach the ladder. This change writes those rules.

Grounding facts (verified this session):
- Domain transport verdicts are coarse: `raw.py` maps 404→`not_found`, 429→`rate_limited`, and both `>=400` (incl. 403) and `>=500` → `connection_error`; exceptions map `timeout`→`timeout` and DNS/SSL/plain-connection → `connection_error`. So 403, 5xx, and network drops are **all** `connection_error` at the domain level.
- Every main tier-failure observation already carries the raw `status_code` (`fc.observe(..., status_code=tier_result.status_code)`). Status-0 means "no HTTP response" (network / DNS / TLS / timeout). So the rules discriminate on `(verdict, status_code)` — **no verdict-splitting in the tiers**.
- `Observation.authoritative` already exists (set for `site_handler` `not_found`, read by the Reddit-comment archive rule) — the precedent for "corroborated 404".
- The existing `_RULES` priorities: `CRITICAL` (arxiv rewrite), `HIGH` (gate-browser signal), `MEDIUM` (reddit-comment archive), `LOW` (cloudflare/paywall archive, `paid_last_resort` declared last).

## Goals / Non-Goals

**Goals:**
- No transport/status failure falls off the tree: 403 / 5xx / other-4xx / `timeout` / connection-reset / uncorroborated-404 / exhausted-429 escalate to `EscalateBrowser`, then the existing ladder carries them to archive/paid/loud-terminal.
- Preserve the three deliberate terminal leaves: genuine DNS NXDOMAIN, authoritative 404, thin-2xx-no-fingerprint.
- Cost discipline: return `EscalateBrowser` only (never `EscalatePaid` directly); LOW priority so specific signals win; caps and termination unchanged.

**Non-Goals:**
- NOT output-preservation — this change intentionally widens escalation (contrast Step 1).
- NOT splitting `connection_error` into per-status verdicts in `raw.py`/`jina.py` — the `status_code` on the log is the discriminator.
- NOT the shelf `dns_error` split (Step 0) itself — this change *consumes* it.
- NOT changing caps (browser 2, paid 1), the ladder order, or the loud ADR-0009 terminal.

## Decisions

**D1 — Rules discriminate on `(verdict, status_code, authoritative)` read from the last tier observation; no new verdicts.** Rationale: the log already carries everything needed; adding verdicts to `raw.py`/`jina.py` would be a wider, redundant change and would fight the coarse-verdict design. Alternative — split `connection_error` into `forbidden`/`server_error`/`network_error` verdicts: rejected, the status_code already encodes it and downstream `resolve_verdict` would need re-tuning for no benefit.

**D2 — One rule per ambiguity class, at LOW priority, returning `EscalateBrowser`.** Concretely: `forbidden_403_escalate` (connection_error + status==403), `server_5xx_escalate` (connection_error + status>=500), `other_4xx_escalate` (connection_error + 400<=status<500, excl. 403), `timeout_escalate` (verdict timeout), `network_drop_escalate` (connection_error + status==0 AND not dns_error), `uncorroborated_404_escalate` (not_found + not authoritative), `exhausted_429_escalate` (rate_limited). Each guards `browser_dispatches < 2` (so it can't spin) and returns `EscalateBrowser`. Rationale: LOW keeps them below the HIGH gate-browser signal and the specific archive heuristics — a content-based decision always wins; these are the catch-all floor. They sit ABOVE `paid_last_resort` in effect only because browser is cheaper — but since they return `EscalateBrowser` and `paid_last_resort` returns `EscalatePaid`, on the first pass the browser rules fire; once the browser cap is spent and the result is still a wall, `paid_last_resort` (which keys on a wall gate_outcome) fires. Confirm the interaction produces browser-before-paid. Alternative — one mega-rule with an internal switch: rejected, it violates the one-rule-one-identity-and-test-pair contract and hides the per-class priority reasoning.

**D3 — DNS carve-out depends on Step 0 (`http-fetch` `dns_error`); this change plans the correct version.** `network_drop_escalate` fires on status-0 `connection_error` **only when it is not `dns_error`**. Until Step 0 lands and a2web maps `FetchVerdict.dns_error` → a terminal `Verdict.dns_error` (new) at `tiers/raw.py::_TRANSPORT_TO_DOMAIN`, a status-0 `connection_error` cannot be told apart from NXDOMAIN. **Decision: Step 0 is a hard prerequisite** — the design is written correct-first. *Interim fallback if Step 0 slips:* let `network_drop_escalate` fire on ALL status-0 `connection_error`; a genuinely-dead domain then incurs one wasted, capped browser (+ maybe paid) attempt before the loud terminal — rare and bounded, never wrong (just slightly wasteful). This fallback is a one-line guard change, easy to tighten when Step 0 arrives.

**D4 — Escalate to browser, not paid.** The rules never return `EscalatePaid`; the free self-hosted browser rung (fast→robust, cap 2) is tried first, and the existing `paid_last_resort` LOW rule handles the paid egress only after browser is exhausted and the result is still a wall. Rationale: preserves the cost-discipline the ladder already encodes; a transport failure is not evidence that paid will succeed where free browser won't.

**D5 — The rules feed the ADR-0009 loud terminal; they do not replace it.** A failure that survives browser + archive + paid ends exactly as today: `status: failed`, `retrieval_incomplete: true`, populated diagnostics + narrative, and the critical `try_user_browser` hint (the late never-silently-miss emission). This change only ensures the ladder is *attempted* before that terminal — the terminal itself is unchanged. Rationale: the floor is the product invariant; we widen what reaches it, not what it does.

## Risks / Trade-offs

- **[Risk] Escalating a genuinely-dead domain (real 404 / real 500 / real NXDOMAIN) wastes a browser+paid attempt.** → Mitigation: DNS NXDOMAIN is carved out (D3, via Step 0); authoritative 404 is carved out; the remaining real-dead cases (a real 500, a real soft-404) incur one *capped* browser attempt (+ paid only if a key is configured) — bounded cost, and the alternative (trusting a status code a WAF can forge) is the ADR-0009 violation we're fixing. Net: correctness over a rare, bounded waste.
- **[Risk] A new rule spins (re-fires forever).** → Mitigation: every rule guards `browser_dispatches < 2`; once the cap is spent the rule returns None and the ladder proceeds to paid/terminal. A dedicated test asserts no rule re-fires past its cap.
- **[Risk] browser-before-paid ordering breaks** (a transport rule and `paid_last_resort` both eligible). → Mitigation: transport rules return `EscalateBrowser` and guard on `browser_dispatches`; `paid_last_resort` keys on a wall `gate_outcome` + `paid_dispatches < 1`. On a bare transport failure there is no wall `gate_outcome` yet, so `paid_last_resort` does not fire until a browser render produced a still-walled gate outcome. A test asserts the sequence browser → (regate) → paid on a persistent transport wall.
- **[Trade-off] Intended output change breaks existing "fails fast" tests.** → Accepted and explicit: those expectations are updated to escalate-then-fail. This is the point of the change; the D-for-Step-1 output-preservation bar deliberately does not apply.
- **[Risk] `status_code` missing on some failure observation the rules read.** → Mitigation: audited — the main tier-failure observe carries it; `proxy_unavailable` is status-0 by design (no HTTP response) and gets its own treatment (proxy failure is retried at the proxy layer, not escalated to browser — confirm it is NOT swept into `network_drop_escalate`).

## Migration Plan

Ship behind `make check` + `make arch`. No data migration, no wire change, no feature flag. Rollback is a plain revert. **Sequencing: land Step 0 (shelf `dns_error`) first**, then this change consumes it; if Step 0 is delayed, ship the D3 interim fallback (escalate all status-0 `connection_error`) and open a one-line follow-up to tighten once `dns_error` is available.

## Open Questions

- Exact placement of the transport rules relative to the existing LOW archive rules (cloudflare/paywall) — do any transport cases want archive *before* browser (e.g. a 403 on a static article that Wayback has)? Default: browser first for all; revisit if a corpus case shows archive-first is materially better for a class.
- Whether `other_4xx_escalate` should exclude 401/451 (auth-required / legal) as non-escalable — a 401 won't be passed by an anonymous browser. Candidate carve-out; decide against real cases during implementation (a 401 may still merit the loud terminal rather than a wasted browser attempt).
- Whether `proxy_unavailable` should escalate at all (it is a local proxy-pool exhaustion, not a site wall) — lean No; confirm it is excluded from the transport rules.
