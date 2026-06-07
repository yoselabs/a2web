# ADR-0006 — Answerability signal and two-stage escalation

**Status:** Provisional — **necessity precondition NOT met** (investigated 2026-06-07); recommend **do not build as specified** pending decision
**Date:** 2026-06-06 · **Investigated:** 2026-06-07
**Supersedes:** —
**Superseded by:** —

> **Provisional ADR.** Direction agreed 2026-06-06. The necessity precondition
> below was the gate before building — it was investigated 2026-06-07 and the
> evidence says the explicit signal is **not** justified. See the finding.

> ## Necessity-precondition finding (2026-06-07) — behavioral signals already deliver answerability
>
> Three live probes of the "answer genuinely absent" case (the substrate's
> question for this ADR):
>
> | Page | Question (answer absent) | Behavior |
> |------|--------------------------|----------|
> | Metacritic Zelda reviews | retail price in USD | `answer`: "does not contain pricing information" (no fabrication); `obstacle: empty`; `try_url` → Switch product page, *"typically links to retailer pricing"*; 4 `ask_here` |
> | Allrecipes banana bread | who invented it / first published | `answer`: "does not contain information about the original inventor" (no fabrication); `obstacle: empty`; `try_url` → banana-bread gallery; 3 `ask_here` |
> | Vercel pricing (Next.js SPA) | Pro plan price | server-rendered via raw (10,251 chars); answer found ($20/mo) — the "JS-unrendered" gap did not even arise |
>
> The behavioral stack — the LLM's honest **non-fabricated** "not present"
> answer + `obstacle: empty` (page-level) + **question-conditioned `try_url`**
> (where the answer likely is) + `ask_here` (what this page CAN answer) —
> already delivers exactly the question-relative answerability + descent that
> this ADR set out to add. No fabrication was observed; `try_url` reasons were
> question-conditioned and useful.
>
> The one place behavioral signals *could* fall short — Stage-2's target:
> answer **present but JS-unrendered**, gate=ok, yielding a *false* "not
> present" — proved narrow in practice: modern sites SSR (Vercel returned full
> content via raw), and a true empty shell already trips the existing
> thin-content → browser gate. No clean reproduction was found.
>
> **Recommendation:** do **not** build the explicit answerability enum + the
> two-stage escalation. The semantics agent already flagged the enum overlaps
> `obstacle`/`confidence` and raises router-JSON wobble-drop risk (~10%→~30%),
> threatening the critical `answer` field — cost the substrate now shows buys
> nothing the behavioral signals don't already provide. If a future *captured*
> regression demonstrates the present-but-unrendered gap, address it with a
> **targeted** browser-escalate-on-not-present-when-JS-shell-detected, never a
> blanket enum. (Magic budget: ADR-0001.)

## Context

Answerability — "did this rung yield what *this question* needs?" — is the descent signal ADR-0002 rule 4 names. Making it real touches both the response envelope and the orchestrator's escalation phase. Two agent findings sharpen it.

## Decision (provisional)

Model **answerability** as a clean, question-relative completeness signal, always emitted by the LLM, and wire a **two-stage escalation** model so it can drive ladder descent:

```
  Stage 1 — deterministic PRE-extraction gate (cheap): commerce-intent + zero answer-token → descend before the LLM call
  Stage 2 — LLM-informed POST-extraction descent: answerability=not_present & needed → descend, with explicit
            decision-log RE-PROJECTION (does not violate "Verdict is a pure projection of the log")
```

## Forces / constraints (from agent review — must be satisfied)

- **Phase-inversion (architecture agent — the deepest finding):** answerability comes *out of* the LLM, which runs *after* today's single gate→escalate→extract loop. The change must introduce a proper post-extraction descent with decision-log re-projection, respecting the browser-≤1/fetch cap and the "Verdict = pure projection of the decision log" invariant. This is an overarching orchestrator change, not a field bolt-on.
- **Semantics (semantics agent):** do **not** ship a 4-value enum (`answered/partial/not_present/uncertain`) — it overlaps `obstacle` (page-level) and `confidence`, and raises router-JSON wobble-drop risk (~10%→~30%). Model as **boolean + freeform reason** (or the minimal cut that is low-variance and distinct from obstacle/confidence). Watch the critical `answer` field's drop risk.
- **Necessity precondition (scope agent + reality):** the original empty `try_url` was caused by *content starvation*, now fixed. Before building an explicit signal, the eval substrate must show whether behavioral `ask_here`/`try_url` already deliver answerability post-fix. The Confirm-by gate must answer "is the explicit signal even needed, and where do behavioral signals fall short?"
- **Ask First:** this changes the `AskResponse` envelope shape — requires explicit envelope sign-off (CLAUDE.md).

## References

- ADR-0002 (rule 4); architecture + semantics + scope agent reviews (2026-06-06)
- `fetcher.py` (`_phase_gate_and_escalate`, `_phase_extract_answer`); `actions/playbook.py`; `decision_log.py`
- BACKLOG: router-shape `page_kind_confidence` was deliberately dropped (v0.21) on the theory behavioral signals suffice — this change must engage that prior decision directly.
