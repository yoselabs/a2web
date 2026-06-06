# ADR-0002 — Real surface is ground truth; upstream extraction is an optimization ladder

**Status:** Accepted
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

## Context

The 2026-06-06 explore session (this conversation) began with a single bug: `ask` on a Hepsiburada product-listing URL returned "no pricing visible… click into individual product pages," with no drilldown links and a false `obstacle: empty` — despite the page carrying a JSON-LD `ItemList` of 36 products each with `offers.{price, priceCurrency, url}`. The immediate cause was a lossy markdown synthesizer (`domain.py::_rows_to_md_table`) that skipped nested dicts and kept only `name | image`. That was fixed and shipped as change `listing-offer-lift`.

The root cause, as a **class**, is bigger: a *lossy projection gated by a value-blind proxy*. The synth selected fields by a structural heuristic (`skip dicts`) whose selectivity is anti-correlated with value (the price/url live inside `offers`, a dict), and the quality gate that governs whether synth replaces trafilatura keys on **length** (`len(synth) > len(original)` — `fetcher.py:1102`), which cannot detect the failure. The repo already fights this class everywhere else (the wobble typed funnel, the no-`dict[str,Any]` arch rule, closed enums — ADR-0001) — it survived only in the one corner that stayed untyped.

The deeper reframing that organizes the whole pipeline: **the canonical truth is what a human user sees in a rendered browser.** Structured-data extraction (JSON-LD, microdata, framework state), markdown synthesis, and trafilatura prose are all **optimizations** that approximate that surface to save cost, time, and bot-protection risk. The synth bug happened because an optimization (markdown synth, whose only job is to cut LLM token cost) silently took on a *fidelity* responsibility (which fields survive) it was never designed to honor, with nothing measuring the resulting fidelity debt.

Five axis-specialised agents (cost, architecture, eval-methodology, semantics, scope) pressure-tested the proposed responses. Their findings are folded into ADR-0003 (the seam) and the provisional ADRs 0004–0007 as design constraints.

## Decision

Adopt the **optimization ladder** as the governing model for fetch+extract. Each rung approximates the real rendered surface; cheaper/higher rungs carry more bias and **owe a fidelity debt** that must be either *checkable against* or *fall back to* a lower rung.

```
   cost↑ bias↑                  OPTIMIZATION LADDER                   fidelity debt owed
   ┌───────────────────────────────────────────────────────────┐
   │ WebMCP (future)   site's own agent API                     │  trust the site's contract
   │ structured data   JSON-LD / microdata / framework state    │  check vs rendered, or descend
   │ raw HTML + traf.  curl_cffi → prose markdown               │  answerability probe
   │ ─────────────────────────────────────────────────────────│
   │ BROWSER RENDER    Camoufox — what the user sees  ◀ TRUTH   │  none — this IS the surface
   └───────────────────────────────────────────────────────────┘
```

Normative principles (the rules the architecture must satisfy):

1. **The rendered browser surface is canonical truth.** Every upstream layer is an optimization that approximates it. A layer is never the product; it is a shortcut past the browser.
2. **Every optimization carries a fidelity debt.** It must be *checkable against* a lower rung (e.g. reconcile structured price vs rendered price) or *fall back* to one (descend the ladder). An optimization that can silently diverge from the surface without a check or a fallback is a defect.
3. **Volume is never a proxy for fidelity.** Length, byte-count, "non-empty," and "longer than the alternative" are banned as quality gates. The gate must measure whether the *answer-bearing signal* survived, not how much text did.
4. **Answerability is question-relative and governs descent.** "Did this rung yield what *this question* needs?" is the signal that decides whether to descend the ladder or answer honestly that the surface lacks it. (Modeled in ADR-0006.)
5. **Optimizations distil; they do not interpret.** Field selection, dedup, and reconciliation are interpretation and belong to the LLM or to a typed contract — never to a value-blind heuristic in deterministic code. (The seam: ADR-0003.)

## Consequences

**Positive**

- Explains the bug class and prevents its siblings: the synth's job (token-cost optimization) is now distinct from fidelity, and fidelity debts are explicit.
- Gives the orchestrator a coherent **descent rule** (answerability-driven) instead of ad-hoc tier escalation heuristics.
- Unifies disparate surfaces (structured data, browser, future WebMCP) under one model with one obligation.
- Predicts, rather than discovers, the failure modes of naive responses (e.g. the "menu" dedup-as-interpretation leak — see ADR-0003/0005).

**Negative / accepted cost**

- Descending the ladder costs time and tokens (browser render, larger LLM context). This is accepted: correctness against the real surface outranks per-fetch cost. Cost is *measured*, not assumed away — see the eval substrate (change 1).
- Measuring fidelity/answerability requires a real eval substrate spanning the failure classes; without it, the principle is unfalsifiable. Hence the substrate is built **first**.
- Several downstream changes (multi-source input, answerability signal) touch the response envelope and reach the extractor seam — these are CLAUDE.md "Ask First" surfaces and require explicit envelope sign-off.

**Rejected posture**

- **"Patch the symptom and defer the rest."** The shipped `listing-offer-lift` fixed one symptom; treating that as sufficient and backlogging the class with "trip conditions" was explicitly rejected. The goal is to fix the class correctly, paying the overarching cost, not to minimise change.

## Implementation

A five-change program executes this ADR, sequenced in `docs/architecture/extraction-fidelity-program.md`. The eval substrate (change 1) lands first as the measurement instrument; each subsequent change confirms a provisional ADR (0004–0007) on completion.

## References

- ADR-0001 — Structural prevention over vigilance (the discipline this extends)
- `openspec/changes/archive/2026-06-06-listing-offer-lift/` — the symptom fix that surfaced the class
- a2web explore-session findings + five axis-specialised agent reviews (this conversation, 2026-06-06)
- `docs/architecture/extraction-fidelity-program.md` — the program roadmap
