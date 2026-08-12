# ADR-0020 — Grounded absence: never surface an absence the page contradicts (product tenet)

**Status:** **Accepted** (decided 2026-08-12)
**Date:** 2026-08-12
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0014 (grounded URLs only — this is its mirror image), ADR-0009 (never silently miss a URL — this extends the floor from URL to page-section), ADR-0006 (declined `answerable: false`; §46 of ADR-0009 leaves the reconciliation trigger this ADR fires), ADR-0017 (effort and confidence proportional to evidence), ADR-0019 (failure-envelope field tiers), openspec change `flag-interaction-gated-sections`

## Context

ADR-0014 established one direction of the grounding contract: a2web may not
emit a URL the page does not contain. The **inverse** was never stated, and it
failed in production.

**The incident (2026-08-12).** A query — `soru cevap sorular cevaplar, seller
Q&A questions and answers full text` — was run against a Hepsiburada product
page. a2web returned:

```json
{"confidence":"high",
 "answer":"No seller Q&A or question-answer content is present on this page for the Carraro Gravel G2 bike."}
```

The page's own rendered text contains:

```
Ürün Açıklaması
Değerlendirmeler
1
Soru Cevap
4
```

The page **states that 4 questions exist**. a2web read that body, failed to
retrieve the questions, and reported their absence — with `confidence: high`
attached, because `confidence` is computed from `(verdict, len(content_md))`
and says nothing about the answer.

The Q&A content sits behind a `<button>` with no `href`. Activating it does not
change the URL (verified by live probe). No a2web browser backend can click —
the shelf `RenderedPage` interface exposes `scroll_to_stable` and nothing else.
So there is no URL to follow and no rung to escalate to.

Three separate rules already in `AGENTS.md` describe this failure, and none of
them was wired to reach it:

- *"Never let a later stage discard a producer's own claim — ADD to an index, never silently replace or relabel it."*
- *"Never declare a truncation against a number that cannot differ — read the SOURCE-stated total."*
- *"Never let a degraded sub-fetch render as absent-at-source — mark the section, emit `section_unretrieved`."*

The third has exactly one producer (`handlers/github.py`), reachable only when a
handler *knows* its own sub-fetch failed. A generic tier never knows.

## Decision

Elevate the inverse of ADR-0014 to a product tenet:

> **a2web may not surface an absence that the fetched page contradicts.** When
> the page's own content asserts that material exists — a section label, a
> stated count, a tab, a disclosure control — and a2web did not retrieve that
> material, the envelope SHALL report it as **unretrieved**, never as absent at
> source. The page's own text is the authority in both directions: a2web may not
> invent what the page does not contain (ADR-0014), and may not deny what the
> page does contain.

Symmetry with ADR-0014, stated once:

| | rule |
|---|---|
| **ADR-0014** | never surface a URL the page does **not** contain |
| **ADR-0020** | never surface an absence the page **contradicts** |

**Enforcement is structural, at three layers** (full mechanism in the openspec
change):

1. **Detection is deterministic and reads raw HTML, not `content_md`.** The
   discriminator for a gated section is *markup* — `role="tab"`,
   `aria-controls` resolving to an absent or empty panel, `<details>` without
   `open`, `aria-expanded="false"`. Markdown erases it: measured against the
   real converters, a `<div role=tablist><button>` tab strip is **dropped
   entirely** by trafilatura, which is the converter on the `raw` tier that
   serves this page. A detector over `content_md` would be reading a body from
   which the evidence had already been removed.
2. **Relevance is judged by the extractor, not by the server.** The detector is
   recall-oriented and deliberately imprecise (cart badges, ratings, prices and
   pagers all share the `label + number` text shape). The gated labels are
   injected into the extractor's input as **grounded handles**, exactly as page
   links are under ADR-0013, and the model selects which gate blocks *this*
   question. Deterministic term-overlap cannot do this job: the motivating case
   has **zero** token overlap between the query (`seller Q&A questions and
   answers`) and the label (`Soru Cevap`).
3. **The envelope reports it as a retrieval hole, not a failure.** An
   `interaction_required` operator hint names the section, relays the
   source-stated count, states that **no other URL exists** and that
   **re-querying is futile**; `confidence` is capped `high → medium`.

## Key rejections (re-litigation guard — full record in the openspec change)

- **Auto-navigate to a "better" URL.** Impossible for this class (no `href`, no
  URL change — probed live) and wrong on principle for the class where a URL
  *does* exist: choosing which page answers the question is the caller's
  decision, not a2web's (ADR-0012). `other_pages{drilldown}` already serves that
  case and correctly hands the decision back. Note the distinction from
  `RewriteUrl` in the planner: that is *the same resource at a different
  address*, never a different resource.
- **`retrieval_incomplete: true`.** Structurally unavailable: the envelope
  contract binds `retrieval_incomplete` to `status: failed` + a non-empty
  `narrative`. The page *was* retrieved and the primary object is intact;
  failing the whole fetch is the worse trade. `retrieval_incomplete` remains
  URL-scoped, per ADR-0019.
- **`confidence: low`.** `low` is reserved — every path to it means a non-ok
  verdict, an extractor-reported page-level obstacle, or no answer at all.
  Shipping `low` here would make a click-gate indistinguishable from
  `ask_unanswered`/`blocked`, which is precisely the state where "retry another
  route" *is* the right action — contradicting the hint's own instruction that
  re-querying is futile. `medium` is the value three existing caps already chose
  for "a retrieval rung had a hole but real content landed"
  (`served_url_differs`, `query_title_mismatch`, failed browser rung).
- **A new envelope field (`unretrieved_sections`, or a `loaded/total` pair).**
  Fails the repo's own caller-actionability test for envelope width: on a query
  the gate does not block, the field would ship with no hint and nothing the
  caller can do. A count earns a field when it drives a decision —
  `items_total` gates a scroll render; this count gates nothing, because no
  click rung exists. Additionally, `content_expectations.assess` defines
  `loaded=0, total>0` as **`fail`** — the presence axis, deliberately excluded
  from `partial` — so filing a gated section there would reinterpret the
  ADR-0009 floor as a fourth normal state.
- **Reusing the `section_unretrieved` hint code.** Same observable, opposite
  fix: its `fix` reads *"usually an API rate limit; retry later, or set a
  credential"*, which is actively harmful advice for a wall no retry passes.
  This is the `extraction_empty` / `llm_error` precedent — two codes for one
  observable **because the honest fix differs completely**.
- **A new `confidence` level ("high confidence that retrieval is incomplete").**
  A value from a different axis smuggled into an ordinal enum. Five sites
  compare `== Confidence.high`; the downgrade-only ("caps never raise")
  invariant is stated three times in `openspec/specs/fetch-response/spec.md` and becomes
  unstateable.
- **A general `query_unanswered` boolean.** Deferred, not rejected. A flag is
  only as good as its negative: set from one detector, `false` would ship on
  every other response asserting a coverage guarantee a2web has not verified. It
  needs a producer census across every path that fails to answer a query — its
  own change, and the reconciliation ADR-0009 §46 anticipates.
- **Adding a click rung to the browser tier.** Blocked on substrate: no shelf
  backend can click. When one exists, this ADR's detection feeds it unchanged
  and the hint becomes the fallback — which is why detection and remediation are
  separable from day one.

## Placement — AGENTS.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / ADR-0012 / ADR-0014 precedent: a single product's behavioral
invariant belongs in a2web's `AGENTS.md` "Never" section with rationale here,
not in `CONSTITUTION.md` (substrate governance).

## Consequences

- One new `HINT_CODES` member (`interaction_required`) — a contract change, not
  an envelope-shape change (precedent: `query_title_mismatch`), so it does not
  trip the `AGENTS.md` "Ask First" gate.
- No new envelope field, no `_TSV_FIELDS` change, no `FetchContext` member, no
  CLI-contract delta, no wire-golden re-bless.
- The detector must read `fc.body`. On `jina`/`firecrawl` the body *is*
  markdown and no raw HTML exists — those tiers get the text-shape fallback only
  and will have lower recall. This is a stated limitation, not a defect.
- `confidence` gains a **declared meaning** (retrieval quality, not answer
  trust) in the `Confidence` docstring and the `query` tool description, and
  `operator_hints[].code` is declared as the agent branching surface. Today
  neither is documented anywhere a caller can see, which is the root of the
  "low means retry" misreading.

## Re-evaluation triggers

- If a shelf browser backend gains a click/expand capability, promote
  remediation from hint to escalation (joins the deferred
  `single-source-escalation-policy` consolidation as its third case).
- If the general `query_unanswered` flag is ever added, reconcile it with this
  hint and with `retrieval_incomplete` (ADR-0009 §46).
- If eval shows the extractor systematically ignores injected gate handles,
  reconsider a deterministic relevance conjunct despite its cross-language
  weakness.
- If gated-section detection proves noisy on the corpus, tighten the DOM
  predicate before weakening the hint — the hint's value is that it is rare.
