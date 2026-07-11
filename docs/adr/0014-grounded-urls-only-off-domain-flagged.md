# ADR-0014 — Every surfaced URL must be on-the-page; off-domain targets are flagged (product tenet)

**Status:** **Accepted** (decided 2026-07-11)
**Date:** 2026-07-11
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never silently miss a URL — a memory-URL is the inverse failure: a *manufactured* hit), ADR-0012 (never manufacture a selection — sibling tenet), ADR-0013 (the closed-set handle mechanism that enforces this for `try_url`), openspec change `surface-page-links-to-extractor` (full record: D11, D14)

## Context

a2web is a **grounded fetcher**. The caller — itself an AI agent with its own world knowledge — trusts every URL a2web hands back as *page-derived*, not invented. Two ways that trust breaks:

1. **Memory / guessed URLs (D14).** Once the extractor is shown real links (ADR-0013), the closed-set handle rehydration guarantees `try_url` URLs are page-anchored. But the A/B eval (`findings_2026-07-11-answer-inline-links.md`) showed the model **already writes raw URLs into the `answer` prose unprompted** (the pypi case wrote `python-httpx.org` from training). That is a backdoor around the closed-set guarantee: the answer text. A memory-URL presented as grounded is a trust violation *exactly when it is wrong* — the same class of harm as the originating guess bug, laundered through prose.

2. **Injected off-domain URLs (D11).** Closed-set rehydration kills *hallucinated* URLs but **launders injected ones**: a page author's anchor labeled "full specifications" pointing anywhere gets a server-blessed `reason` handed to an autonomous agent. Anchor labels are attacker-controlled input.

## Decision

Two coupled rules, elevated to a product tenet:

> **Every URL a2web emits — in `try_url` OR inline in `answer` prose — must be traceable to the fetched page:** either a `{{n}}` digest handle (an anchor href) or a URL that appears **literally in the page content**. A URL produced from the model's training knowledge or by pattern-guessing (`…/reviews`, `…-yorumlari`) is forbidden. When the needed link is not on the page, a2web says so (ADR-0009 honest absence) rather than inventing it.

> **Off-domain rehydrated targets carry an explicit wire flag** (`NextUrl.off_domain`) and require **question-conditioned** justification, not genre justification. Same-domain and off-domain carry very different trust.

**Enforcement is structural, at two layers:**
- **Prompt (D14):** the `EXTRACT_ROUTER_V1` "LINKS IN THE ANSWER · HARD RULE" clause (v4) permits the model to weave a `{{n}}` handle into the answer (server rehydrates it to a real URL — a self-contained answer) but forbids any URL not on the page.
- **Closed-set rehydration (D11/ADR-0013):** `try_url` handles are validated against the digest table; `off_domain` is computed by registrable-domain compare and flagged on the wire.

v4 confirmation eval: the HARD RULE **demonstrably shifted the model off memory-URLs onto grounded anchors** (the pypi doc/source links came from real anchors, not training).

## Key rejections (re-litigation guard — full record in the openspec change)

- **Post-hoc strip any answer URL not in the closed digest set (D14)** — too blunt: the digest is built from `<a href>` anchors, so it would also strip **grounded page-text URLs** (visible plain-text URLs the model faithfully copied — the pypi case), discarding good data. The prompt lever forbids the *ungrounded* class at the source without endangering the *grounded* one. Governing principle (owner, 2026-07-11): **as long as the link was on the page, it is fine.**
- **Encourage the model to supply useful links from its own knowledge (D14)** — it may be right (a famous library) but a2web cannot distinguish correct-from-memory from confabulated-from-memory; presenting an unverifiable URL as grounded breaks the retrieval contract. The caller has its own LLM for world knowledge.
- **Provenance-flag every answer URL as verified/unverified (D14)** — deferred, not rejected: adds wire surface; the prompt prohibition is the cheaper first move. Revisit if the model ignores the HARD RULE in practice (eval will tell).
- **Treat all rehydrated links as equally trusted (D11)** — ignores that anchor labels are attacker-controlled and off-domain redirection is the injection vector.

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / ADR-0012 precedent: this is a single product's behavioral invariant. It belongs in a2web's `CLAUDE.md` "Never" section with rationale here, **not** in `CONSTITUTION.md` (verbatim a2kit-synced substrate governance — a product tenet there would pollute shared governance and break the sync contract).

## Consequences

- Additive wire field `NextUrl.off_domain` (omitted when `False` — backward-compatible).
- The `answer` prose is rehydrated (`_phase_extract_answer` runs `rehydrate_text`): a stray `{{n}}` becomes a real URL or is dropped, never leaked. `{{n}}` is collision-safe so real answer text is untouched.
- **The `.format()` quad-brace hazard:** marker instructions must be written `{{{{n}}}}` in prompt source so `.format()` emits the literal `{{n}}` the digest uses — a bare `{{n}}` collapses to `{n}`, which `rehydrate_text` misses, leaking the raw handle. Locked by `test_router_handle_markers_render_double_brace`.

## Re-evaluation triggers

- If the model ignores the HARD RULE in practice (eval surfaces ungrounded answer URLs), add the deferred provenance flag (verified/unverified) to answer URLs.
- If off-domain suggestions prove low-value or high-risk in the uptake telemetry (openspec D12 / task 8.2), tighten from flag to same-domain-only.
- If the deployed extractor model changes, re-confirm the HARD RULE holds against it.
