## Context

The content gate (`packages/block_detector.py::evaluate`) classifies a fetched body into a closed-enum `BlockVerdict`. Its thin-page branches all key on `len(content_md) < LENGTH_FLOOR` — the length of the **extracted** markdown. Three thin sub-cases escalate today (turnstile/anubis/baxia markers, a `cf_iuam` interstitial, and a JS-shell `js_required` match); a thin page matching **none** of them returns a bare `BlockVerdict.length_floor` with `escalation=None` (`block_detector.py:237-238`). The `quality-gate` spec pins this as deliberate ("Sites without ANY marker SHALL continue to return `length_floor` ... preserving today's behavior") — precisely to avoid false browser escalations on legitimately-short or ambiguous pages.

That carve-out was written about pages with **real raw HTML that extracts thin**. It does not speak to the distinct, narrower population this change targets: a response whose **raw body is itself essentially empty** — near-zero visible text — which is a classic silent-block tell (a WAF serving an empty shell to a non-browser client). Because extraction of an empty body yields empty `content_md`, these pages currently fall into the same bare `length_floor` terminal, indistinguishable at the verdict level from a genuinely-short-but-present page.

Step 2 (`escalate-on-status-derived-walls`) established the pattern: an ambiguous wall is escalated through the (now unified, now reachable) ladder, and only a genuine terminal ends the cascade. A blank raw body is such an ambiguous wall.

## Goals / Non-Goals

**Goals**
- Detect a near-empty **raw HTML** body as a distinct `blank_page` verdict, separate from extracted-thin `length_floor`.
- Escalate `blank_page` through browser → paid scraper before conceding.
- End a surviving `blank_page` as a loud, honest terminal failure with a signal-accurate hint.

**Non-Goals**
- Changing extracted-thin `length_floor` behavior for pages with substantial raw HTML (untouched).
- Distinguishing "silently blocked" from "genuinely empty" — we cannot, and treat both as a loud miss (ADR-0009 conservative floor).
- Re-using `try_user_browser` for this terminal (a genuinely empty source is not a browser-passable wall).

## Decisions

**D1 — Signal = raw-HTML visible-text emptiness, not `content_md` thinness.** The new branch computes visible text from `raw_html` (strip tags + collapse whitespace) and fires when it is below `BLANK_HTML_THRESHOLD` (small, near-zero — order of ~64 chars, tuned so `<html></html>`/empty shells match but a ~480-char "JavaScript is disabled" stub does not). Keying on the raw body — not the extracted markdown — is what makes this population disjoint from the existing thin-content carve-outs and gives it high precision.

**D2 — New closed-enum verdict `blank_page`.** `BlockVerdict.blank_page` (package) + `Verdict.blank_page` (domain), ranked in `decision_log._verdict_rank` as a wall-class terminal (peer of `block_page_detected`/`anti_bot`). A distinct verdict — not an overloaded `length_floor` — keeps the escalation policy, the terminal, and the hint each keyed on one honest value.

**D3 — Escalation order: browser then paid scraper, on existing rungs.** The gate emits `EscalationSignal(next_tier="browser", reason="blank_page")`; the existing HIGH gate-browser planner rule dispatches the capped browser. If the render re-gates to `blank_page` again, `blank_page` being in `_WALL_VERDICTS` lets `paid_last_resort` carry it to the paid scraper (residential + real browser). No new escalation type; both dispatches respect existing caps (browser ≤ 2, paid ≤ 1), so the ladder terminates.

**D4 — Surviving `blank_page` is a loud wall terminal with the `try_user_browser` hint.** After browser + paid both return blank, the fetch ends `status: failed` + `retrieval_incomplete: true` with the critical `try_user_browser` hint, exactly as the other wall verdicts. *(Revised during live sanity — see the addendum below.)* Original reasoning had emitted a distinct `blank_page` hint on the theory that a genuinely empty source is not browser-passable. Live testing (g2.com) disproved the premise: a near-empty body is far more often a **silent anti-bot block** (403 to every bot, full content in a real browser) than a genuinely empty resource, and the two are indistinguishable from the fetcher's side. Reporting a content-rich walled page as "empty" is the worse (false-negative) error — and for g2 the `blank_page` verdict even *outranked* and suppressed the original 403's own `try_user_browser`. So a surviving blank body gets the shared `try_user_browser` escalation; the `blank_page` verdict is retained only for diagnostics/narrative.

**D5 — Detector ordering.** The `blank_page` check sits *after* every anti-bot marker branch and the `js_required` JS-shell branch, and *before* the bare `length_floor` fallthrough. A shell a fingerprint already claims keeps its specific verdict; only the marker-less near-empty body becomes `blank_page`.

## Risks / Trade-offs

- **Paid-egress cost (the live open question).** Every near-empty raw page now spends up to one browser + one paid scraper request, and paid egress is metered. Mitigation: the population is rare (truly-empty raw bodies), and the raw-HTML keying (D1) is high-precision, so false positives that burn a paid attempt should be uncommon. Decision **for now**: spend the attempt (user steer). Revisit if telemetry shows the paid rung firing on blank pages more than expected.
- **A genuinely-empty legit page reports `failed`.** A URL that legitimately returns an empty document is reported as a blank-page failure. Accepted: it is honest (there is no content), and the distinct hint (D4) tells the caller it was blank, not walled — so they are not misled into a pointless browser retry.
- **Threshold tuning.** `BLANK_HTML_THRESHOLD` too high risks catching short-but-real pages; too low misses padded empty shells. Start conservative (near-zero visible text) and treat as a settings-tunable constant if a real case demands it.

## Migration Plan

Additive: a new verdict value + a new detector branch + a new hint code. No existing verdict changes meaning; no wire field is removed. Contract snapshot (`tool_schemas.json`) gains the `blank_page` verdict enum value + hint code — re-bless. No data migration.

## Open Questions

- **Should a surviving `blank_page` be `retrieval_incomplete` at all, given retrieval "completed" (we correctly got nothing)?** Decision: yes — we cannot distinguish empty-because-blocked from empty-because-empty, and ADR-0009 favors the loud floor. The distinct hint keeps it honest.
- **Aggregate paid cost** (see Risks) — spend for now; instrument and revisit.
- **Does the paid scraper meaningfully un-blank pages the self-hosted browser cannot?** If telemetry shows the paid rung never recovers a `blank_page` the browser already failed, drop the paid step for this verdict and go straight to the terminal after browser.
