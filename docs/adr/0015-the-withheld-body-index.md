# ADR-0015 — The withheld-body index (product tenet)

**Status:** **Accepted** (decided 2026-07-11)
**Date:** 2026-07-11
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (honest incompleteness — a hidden page region is the inverse of a hidden miss), ADR-0012 (exhaustive over the *asked* set — a complementary axis), ADR-0014 (URL grounding, preserved on `other_pages`), openspec change `ask-response-contract-v2` (full record).

## Context

`query` (formerly `ask`) withholds the page body by default (`include_content=False`) for token economy — the body is large, the answer is small. But the caller is itself an AI agent that **never sees the body**; after a fetch it knows the answer to *one* question and is blind to everything else the page holds. Re-fetching to recover that content wastes the scarce resource (the proxy fetch). a2web, having read the whole body, is the only party that knows what else is there.

## Decision

When a2web withholds the body, it MUST leave a **faithful, cheap index of what it withheld**, so the caller is never blind to recoverable on-page content. Two zones, differing in **kind**:

- **`also_here`** — an index of content that IS on THIS page but did not reach the `answer`. Certain (a2web saw it) and cheap to recover (a same-URL re-query is cache-served — no new proxy fetch). Be generous; it is an index, not a curiosity list. Entries are terse **queries** (target + one operator), not hedged questions.
- **`other_pages`** — pointers to content ELSEWHERE (a2web saw only a link). Speculative and expensive (each costs a new proxy fetch). Be sparse; one high-level pointer per URL, question-conditioned when `kind=drilldown`. Unifies the former `next_links` (continuation → `kind=structural`) and `try_url` (question-conditioned → `kind=drilldown`).

Distillation MUST NOT hide recoverable content: presenting a distilled answer while silently dropping load-bearing page regions is the same class of harm as a silent miss (ADR-0009). The index is the remedy.

**Complement to ADR-0012, not conflict.** ADR-0012 keeps the `answer` exhaustive over the *asked* option-space. ADR-0015 governs pointers to the *un-asked remainder*. The index MUST NEVER become an excuse to withhold data that *was* asked for and force a same-page re-fetch (ADR-0012 "One-shot").

**Orthogonality.** The index is `structural_form`-dependent and MUST NOT double-cover its siblings: on prose/product/discussion, `also_here` is the load-bearing index and is dense; on a `listing`, `options` + `refinement_axes` carry "what else is here" and `also_here` stays sparse and never restates a `heading`, an `option` row, or a `refinement_axis`.

**Cost asymmetry is legible, not new wire fields.** The certainty/cost split (`also_here` = cheap cached re-query; `other_pages` = new fetch) is stated in the tool description and this ADR — no per-item cost/certainty wire fields this round (a Re-evaluation trigger covers promoting a signal later if measured worth it).

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / ADR-0012 / ADR-0014 precedent: a single project's product invariant belongs in a2web's `CLAUDE.md` "Never" section with rationale here, not in `CONSTITUTION.md` (verbatim a2kit-synced substrate governance).

## Consequences

- Field family reorganizes: `ask_here` → `also_here` (query-grammar strings); `next_links` + `try_url` → `other_pages` (kind-tagged). `NextUrl`/`NextUrlBoundary` → `OtherPage`/`OtherPageBoundary` with a `kind` field. `FetchResponse` (the `fetch_raw` page envelope) keeps its own `next_links` — the fold is scoped to the `query` envelope.
- `EXTRACT_ROUTER_V1` bumped to version 5: emits `also_here` in query grammar + a unified `other_pages` shape, preserving the ADR-0014 "LINKS · HARD RULE" clause and `{{{{n}}}}` marker discipline.

## Re-evaluation triggers

- If the body-withholding default flips (`include_content=True` by default), the index's rationale weakens — revisit.
- If a per-item cost/certainty signal graduates to the wire (measured worth it).
- If `also_here` is generalized to carry values (not just pointers).
