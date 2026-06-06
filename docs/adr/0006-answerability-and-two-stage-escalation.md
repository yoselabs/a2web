# ADR-0006 — Answerability signal and two-stage escalation

**Status:** Accepted (provisional) · **Confirm-by:** change `answerability-escalation`
**Date:** 2026-06-06
**Supersedes:** —
**Superseded by:** —

> **Provisional ADR.** Direction agreed 2026-06-06; confirmed/revised when the owning change lands and is validated against the eval substrate. The plan carries a reconfirm task. Note the open precondition below: the eval substrate must first establish whether an *explicit* signal is even needed.

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
