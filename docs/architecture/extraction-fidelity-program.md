# Extraction Fidelity Program

A sequenced program of changes executing ADR-0002 (real surface is ground truth;
upstream extraction is an optimization ladder) and ADR-0003 (the deterministic
coarse-select / LLM-interpret seam). Born from the 2026-06-06 explore session that
started with the `listing-offer-lift` bug and generalized it to a class.

## Governing ADRs (Accepted)

- **ADR-0002** — Real surface is ground truth; optimization ladder with a fidelity debt.
- **ADR-0003** — The extraction seam: deterministic coarse-select, LLM interprets.

## Provisional-ADR lifecycle (convention established here)

Per-change ADRs carry `Status: Accepted (provisional) · Confirm-by: <change>`. They
record the agreed *direction* but are not settled. Each owning change's `tasks.md`
includes an explicit **"reconfirm / update this ADR"** task; the ADR is moved to
plain `Accepted` (or `Revised` / `Superseded`) only when the change lands AND is
validated against the eval substrate. Rationale: implementation routinely shifts
decisions; crystallizing the ADR before its change proves it would cement a guess.

## Change sequence

```
  1. eval-substrate ───────────────┐  the INSTRUMENT — built first; everything below is
                                    │  validated against it (don't cement architecture blind)
  2. typed-extraction-boundary ◀────┤  confirms ADR-0004 — structural elimination of lossy projection
  3. multi-source-extraction-input ◀┤  confirms ADR-0005 — the "menu"; retire the volume gate
  4. answerability-escalation ◀─────┤  confirms ADR-0006 — two-stage escalation; answerability signal
  5. real-surface-grounding ◀───────┘  confirms ADR-0007 — rendered DOM first-class; reconciliation
```

Dependencies: 2 depends on 1 (measure before/after). 3 depends on 2 (the typed
boundary is what the menu feeds). 4 is the overarching orchestrator change (phase
model); it depends on 1 for the necessity check. 5 depends on 4 (real-surface tier
first-class). Each step re-runs against the eval substrate.

## Per-change constraints (from the 2026-06-06 five-agent adversarial review)

| Change | Must satisfy (agent finding) |
|--------|------------------------------|
| eval-substrate | live-truth-vs-frozen paradox → three-layer fixtures (raw HTML + rendered DOM + answer); LLM-judged axes stay informational (`make bench`), only deterministic contract/token axes gate `make check`; multiple corpuses (happy-pass regression + breaking A/B/C/JS) with sync; judge-model pinned/tracked. |
| typed-extraction-boundary | package-owned boundary types, no domain imports; reuse `Wobbled`-style funnel; type the answer-bearing schema.org subset, default-keep the tail; arch fitness fn bans the structural-filter projection. |
| multi-source-extraction-input | preserve cache-prefix byte-equality; budget-aware trim vs `max_content_chars`; dedup is LLM-side (coarse subset-suppression only deterministically); `fc.content_candidates` list, not a mutated slot; document+retire the volume gate. |
| answerability-escalation | resolve the phase-inversion (post-extraction descent + decision-log re-projection, browser-≤1 cap, Verdict-as-projection); boolean+reason NOT a 4-value enum; FIRST establish (via substrate) whether behavioral `ask_here`/`try_url` already suffice; Ask-First envelope sign-off. |
| real-surface-grounding | surface conflicts via `OperatorHint(price_mismatch)` before LLM reconciliation; scope to commerce/price; depends on rendered-DOM grounding; token-budget aware. |

## Ask-First gates (CLAUDE.md)

Changes 3 and 4 touch the response-envelope shape / extractor seam → explicit
envelope sign-off required before implementation. The provisional-ADR Confirm-by
process forces that conversation.

## Backlog (noted, out of program scope)

- WebMCP (top-of-ladder surface) · full cross-source atomization · price
  provenance + locale/currency exposure.

## Status

- ADR-0002, ADR-0003: Accepted.
- ADR-0004–0007: Accepted (provisional), confirm-by their changes.
- Changes: `eval-substrate` next (proposal in progress).
