# ADR-0006 — Answerability signal and two-stage escalation

**Status:** **Superseded by behavioral signals** — not built (decided 2026-06-08). Necessity precondition investigated against the substrate; the explicit signal is not justified.
**Date:** 2026-06-06 · **Investigated:** 2026-06-07/08 · **Closed:** 2026-06-08
**Supersedes:** —
**Superseded by:** the existing behavioral stack (`answer` honesty + `obstacle` + `try_url` + `ask_here`)

> **Closed 2026-06-08 — no change authored.** The necessity precondition below
> was the gate before building. It was investigated against the eval substrate
> with 7 live probes; the evidence is decisive that the explicit answerability
> signal + two-stage escalation is **not** justified. The behavioral stack
> already meets the bar. Finding locked below.

> ## Necessity-precondition finding — behavioral signals already deliver answerability
>
> Seven live probes, focused (per the owner's 2026-06-08 steer) on the
> insufficient-information / "the asked key isn't here" case — especially price:
>
> | Page | Question | Data state | Behavior |
> |------|----------|-----------|----------|
> | Vercel pricing | Pro price | present | "$20/month" ✅ |
> | Vercel pricing | **Enterprise** price | key absent *in a data-rich page* | "not fixed — custom, contact sales" — **no fabricated number**, explains why; `try_url` → docs/contact |
> | books.toscrape | cheapest book + price | present (compute) | "Starving Hearts £13.99" — **verified correct** |
> | books.toscrape | price of *The Great Gatsby* | product ABC absent | "not listed on this page … 20 books, none match" · `obstacle: empty` · `ask_here` |
> | allrecipes | price of the KitchenAid mixer | product on wrong-kind page | "page does not mention … no retail price" · `obstacle: empty` |
> | Metacritic Zelda | retail price in USD | absent | "does not contain pricing information" · `obstacle: empty` · `try_url` |
> | allrecipes | who invented banana bread | absent | "does not contain information about the original inventor" · `obstacle: empty` |
>
> **Across all 5 insufficient-information cases: zero fabrication.** Haiku states
> "not present / not fixed / not listed" plainly, explains *why*, and offers a
> recovery path (`try_url` / `ask_here`). The hardest case — a number-shaped
> question where one plan has a number and the asked one (Enterprise) does not —
> is exactly where a weak model invents "$X"; Haiku said "custom, contact sales".
> The two data-present controls answered correctly (computation verified).
>
> **Known nuance (not worth a build):** the insufficiency signal lives in the
> prose `answer` + `obstacle: empty`. `obstacle: empty` fires when the *whole
> page* lacks the data, but **not** for "key absent within a data-rich page"
> (Vercel Enterprise had no `obstacle`) — there is no dedicated
> machine-readable `answerable: false`. An agent branching programmatically on
> "couldn't answer" must read the prose in that sub-case. Adding a boolean was
> weighed and **declined**: the semantics review flags enum/flag overlap with
> `obstacle`/`confidence` and ~10%→~30% router-JSON wobble-drop risk, threatening
> the critical `answer` field — cost with no quality gain (magic budget,
> ADR-0001). If machine-readable insufficiency is ever needed, the right home is
> a **`make bench` answer-quality axis** (live, model-behavior) — a frozen-replay
> cassette cannot guard it (it would just re-serve the recorded answer). Noted as
> a bench backlog item, not built.
>
> The Stage-2 "present-but-JS-unrendered" gap also proved narrow (modern SSR;
> Vercel returned full content via raw; true empty shells already trip the
> existing thin-content → browser gate).

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
