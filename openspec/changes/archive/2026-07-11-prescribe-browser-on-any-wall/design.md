## Context

The `try_user_browser` critical hint is emitted from **three** places in `fetcher._phase_gate_and_escalate`, each guarding a different verdict whitelist, because the phase early-returns at `fetcher.py:1668` (`if not (fc.body and fc.resolved_verdict() is Verdict.ok): return`):

1. inside the `render_requested` branch (forced paid render exhausted),
2. before the early return — `_is_escalatable_transport_wall(fc)` for bodyless transport failures (403/5xx/timeout/…),
3. after the post-gate loop — `resolved_verdict() in _WALL_VERDICTS` for body-bearing content walls (block/anti_bot/paywall/blank_page).

The split exists *only* because the early-return means a bodyless failure never reaches site 3. Each site keys on a hand-maintained verdict list, so a verdict on no list (`length_floor`, `proxy_unavailable`, `other`) gets no hint. `retrieval_incomplete` is set by a parallel mechanism: a wall-verdict tuple in `fetcher_response.py:289` plus a "failed + try_user_browser hint" hook at `:332`.

`g2.com` exposed the gap live: `raw 403 → jina thin 200 → length_floor`, ends `failed`, no hint — and the page is real (1,066 CRM products, confirmed in a real browser; every automation path — curl, headless Chromium, jina — is blocked).

## Goals / Non-Goals

**Goals**
- One systematic rule: any `failed` fetch that isn't genuinely-gone prescribes the browser.
- Delete the verdict whitelists and the three-way emission split.
- `retrieval_incomplete` follows the same rule with no second list to maintain.

**Non-Goals**
- Making a2web embed/drive a real browser — it *prescribes* the caller's (the caller with a native browser integration acts on the hint).
- Naming a specific browser product in the hint (spec forbids it; wording stays capability-generic).
- Re-deciding the browser/paid *escalation ladder* — this change is about the terminal hint floor, not which tiers run.

## Decisions

**D1 — Invert to a genuine-gone blacklist.** Define the set of terminals that end `failed` but must NOT prescribe a browser (a browser genuinely cannot help):
- `Verdict.dns_error` — NXDOMAIN.
- authoritative `not_found` — `any(o.authoritative and o.verdict is Verdict.not_found for o in fc.observations)`.
- `Verdict.content_type_mismatch` — a non-HTML resource *was* retrieved; a browser won't extract it better (see Open Questions).

`paid_auth_error` is special: it prescribes its **own** `paid_auth_error` hint, not `try_user_browser`, but IS `retrieval_incomplete`. Every other `failed` verdict → `try_user_browser`.

**D2 — Single emission chokepoint.** Add `_prescribe_browser_on_wall(fc)` called once at the end of `_run_pipeline` (after `_phase_gate_and_escalate` returns), so it runs for BOTH the bodyless early-return path and the body-bearing path. Remove all three in-phase emission sites, `_WALL_VERDICTS`, `_ESCALATABLE_TRANSPORT_VERDICTS`, and `_is_escalatable_transport_wall`. The helper: `if fc.resolved_verdict() is not Verdict.ok and not _is_genuine_gone(fc) and not _has_browser_hint(fc): append try_user_browser_hint(fc.final_url)`. The Reddit handler's eager hint + `_has_browser_hint` dedup are unchanged (never double-emit).

**D3 — `retrieval_incomplete` derives from the hint.** Keep the existing "failed + `try_user_browser` present → incomplete" hook; drop the now-redundant wall-verdict tuple, retaining `paid_auth_error` as the one non-`try_user_browser` incomplete. Result: `retrieval_incomplete` is true iff the fetch is a real miss (failed + not genuine-gone), computed once, no separate list. Genuine-gone terminals stay `failed` but `retrieval_incomplete` is absent (honest "gone", not "behind a wall").

**D4 — `length_floor` after a wall is the motivating case, but the rule is verdict-agnostic.** We do NOT try to "remember" the discarded 403 or re-rank the projection — that's the `single-source-escalation-policy` concern. The floor keys purely on the *final* state (`failed` + not genuine-gone), so a `length_floor` terminal is covered regardless of how it arose. A legitimately-thin page that ends `length_floor` also gets the hint; that is acceptable and arguably correct — if the gate deemed it a failure, "your browser may render more" is honest guidance, and ADR-0009 favors the loud floor.

## Risks / Trade-offs

- **Over-prescription on legit-thin pages.** A genuinely short page (stub, tiny article) that ends `length_floor` now says "try your browser." Accepted: it's already `status: failed`, so a prescription is consistent; the alternative (silent fail) is the ADR-0009 harm we're removing. If this proves noisy, the narrower fix is upstream (should a short-but-real page be `failed` at all?), not re-adding a hint whitelist.
- **`content_type_mismatch` judgment (Open Questions).** Excluding it assumes "we got a resource, wrong type" ≠ "walled." If a real case shows a browser *does* recover a mismatch (e.g. a page mislabeled as octet-stream that renders fine), move it out of the blacklist.
- **Behavior change is intended and wide.** Any current test asserting a specific failed verdict carries no hint will flip. These are legitimate expectation changes (the whole point), verified case-by-case, not fixture hacks.

## Migration Plan

Pure logic change: remove two constants + one helper + three emission blocks; add one helper + one call site; simplify one `retrieval_incomplete` derivation. No wire-shape change, no new verdict, no data migration, no contract-snapshot change (same fields). Existing hint/incomplete tests updated to the systematic expectations.

## Open Questions

- **`content_type_mismatch`: blacklist or prescribe?** Leaning blacklist (a retrieved non-HTML resource isn't a wall a browser passes). But a mislabeled HTML page that trips the content-type guard *would* benefit from a browser — if that turns up, reclassify. Decision for now: blacklist (no `try_user_browser`), and treat it as retrieved-but-unusable rather than a miss.
- **Should `proxy_unavailable` really prescribe the browser?** It's our infra (proxy pool exhausted), not a site wall — but the caller's own browser bypasses our proxy entirely, so "try your browser" genuinely helps. Decision: yes, prescribe (it's a real miss from the caller's perspective).
