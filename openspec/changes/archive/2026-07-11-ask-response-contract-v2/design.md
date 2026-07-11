# Design — ask response contract v2 (the withheld-body index)

## D0. ADR-0015 (draft — promote to `docs/adr/0015-*.md` on apply)

> # ADR-0015 — The withheld-body index (product tenet)
>
> **Status:** Proposed (drafted 2026-07-11) · **Date:** 2026-07-11 · **Supersedes:** —
> **Related:** ADR-0009 (honest incompleteness — a hidden page region is the inverse of a hidden miss), ADR-0012 (exhaustive over the *asked* set — complementary axis), ADR-0014 (URL grounding, preserved on `other_pages`), openspec change `ask-response-contract-v2`.
>
> ## Context
> `query` (formerly `ask`) withholds the page body by default (`include_content=False`) for token economy — the body is large, the answer is small. But the caller is itself an AI agent that **never sees the body**; after a fetch it knows the answer to *one* question and is blind to everything else the page holds. Re-fetching to recover that content wastes the scarce resource (the proxy fetch). a2web, having read the whole body, is the only party that knows what else is there.
>
> ## Decision
> When a2web withholds the body, it MUST leave a **faithful, cheap index of what it withheld**, so the caller is never blind to recoverable on-page content. Two zones, differing in **kind**:
> - **`also_here`** — an index of content that IS on THIS page but did not reach the `answer`. Certain (a2web saw it) and cheap to recover (a same-URL re-ask is cache-served — no new proxy fetch). Be generous; it is an index, not a curiosity list.
> - **`other_pages`** — pointers to content ELSEWHERE (a2web saw only a link). Speculative and expensive (each costs a new proxy fetch). Be sparse; one high-level pointer per URL, question-conditioned when `kind=drilldown`.
>
> Distillation MUST NOT hide recoverable content: presenting a distilled answer while silently dropping load-bearing page regions is the same class of harm as a silent miss (ADR-0009). The index is the remedy.
>
> **Complement to ADR-0012, not conflict.** ADR-0012 keeps the `answer` exhaustive over the *asked* option-space. ADR-0015 governs pointers to the *un-asked remainder*. The index MUST NEVER become an excuse to withhold data that *was* asked for and force a same-page re-fetch (ADR-0012 "One-shot").
>
> **Orthogonality.** The index is `structural_form`-dependent and MUST NOT double-cover its siblings: on prose/product/discussion, `also_here` is the load-bearing index and is dense; on a `listing`, `options` + `refinement_axes` carry "what else is here" and `also_here` stays sparse and never restates a `heading`, an `option` row, or a `refinement_axis`.
>
> ## Placement
> `docs/adr/0015-*.md` + a row in `docs/adr/INDEX.md` + a "Never" line in `CLAUDE.md`. NOT `CONSTITUTION.md` (substrate governance).
>
> ## Consequences
> Field family reorganizes: `ask_here`→`also_here`; `next_links`+`try_url`→`other_pages` (kind-tagged). Cost asymmetry is documented (not new wire fields).
>
> ## Re-evaluation triggers
> If the body-withholding default flips; if a per-item cost/certainty signal graduates to the wire; if `also_here` is generalized to carry values (not just pointers).

## D1. The query grammar (deletion rule — for `also_here` entries and the caller's own `query`)

```
query = the question with the scaffolding deleted
  DROP the verb frame ("does it" / "are there any")   DROP the already-known page entity
  KEEP the target noun(s)                              KEEP the discriminating operator
operators (free-prior only):  ,  list   ·  vs  contrast   ·  /  alternatives   ·  "exact"  ·  -exclude
emphasis:  CAPS at most one load-bearing token (the decider)
FIND → phrase, no question     DECIDE → keep a "?"      compound `and` → split into two
```

Worked (four shapes): `connection issues: Apple Home only vs all platforms` (fork) · `firmware version of failing units` + `setup steps ONLY in working reviews` (compound, split) · `OFFICIAL troubleshooting / known issues for pairing` (qualifier) · `battery, latency, false-trigger rates` (list). Applied to `also_here`, the deletion rule yields a **content manifest**: `return policy · 6 reviews 3.3★ · full spec table · shipping`.

## D2. The `other_pages` merge

```
other_pages: list[OtherPage]
  OtherPage = { url, reason, kind: "structural" | "drilldown", off_domain (omit when False) }

kind = "drilldown"  iff the link's selection depends on the QUESTION (why THIS url answers the gap)
kind = "structural" otherwise (pagination, handler-known continuation, page-order navigation)
```

- Absorbs `next_links` (→ `structural`) and `try_url` (→ `drilldown`). One TSV block on the wire.
- **ADR-0014 preserved in full:** every `url` is a rehydrated `{{n}}` closed-set handle or literally on the page; `off_domain` trust flag carries over; `drilldown.reason` stays question-conditioned (≤120 chars). Structural links need not be question-conditioned but MUST still be on-page.
- Cap: reconcile the old `next_links` cap (10) with the merged field — propose a single cap (e.g. 10), page-order within `structural`, priority-order within `drilldown`.

## D3. Naming

`ask_here` → **`also_here`** (index of THIS page). Pairs against `other_pages` (elsewhere). `refine` rejected — collides with `refinement_axes`. `on_page` considered; `also_here` reads more naturally as "also available here."

## D4. Cost-asymmetry legibility (cheap default: prose, not wire)

Documented in ADR-0015 + the tool description — `also_here` = cheap cached re-ask (re-query the same URL, body served from cache); `other_pages` = new proxy fetch. No new per-item wire fields this round (a Re-evaluation trigger in ADR-0015 covers promoting a signal later if measured worth it).

## D5. Validation — spikes on the cheap provider ONLY (never metered)

Reuse the harness (corpus, Judge, four axes) via `bench-cost-isolation`'s subscription provider + per-item/per-axis isolation, so each spike is a handful of guarded, stamped calls.

```
SPIKE A  phrasing {sentence, query-grammar, keyword} × 4 shapes → Judge quality + cost
         H: query-grammar lossless vs sentence, cheaper; keyword drops fork + qualifier
SPIKE B  CAPS A/B on fork+qualifier → constraint-respect → prescribe CAPS narrowly or not
SPIKE C  generate queries from LEAN vs FAT description, run through A → ship shortest that holds
```

LEAN (~15w): `query — a concrete, terse search query for what you want from the page, not a full sentence.`
FAT (~50w): adds the operators + CAPS + FIND/DECIDE rule. **Deferred (needs multi-turn eval):** whether terse queries reduce downstream fetch count — the real economy the single-shot harness can't see.
