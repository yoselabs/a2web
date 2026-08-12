# Design — flag-interaction-gated-sections

Tenet: **ADR-0020** (grounded absence). This document records the mechanism and
the decisions behind it. Rejections that guard the tenet itself live in the ADR;
rejections that guard the *mechanism* live here.

## The failure, measured

Live probe of the motivating page (2026-08-12):

```
<button class="…">Soru Cevap</button>     href: null
button.click()  →  location.href UNCHANGED
body.innerText contains:  "Değerlendirmeler\n1\nSoru Cevap\n4"
```

So: the page states 4 questions exist; the content has no URL; and no shelf
browser backend exposes a click — `RenderedPage` offers `scroll_to_stable` and
nothing more. Hint-only is forced by the substrate, not chosen.

## D1 — Detection reads raw HTML, not `content_md`

**Decision:** the detector operates on `fc.body`.

Measured against the real converters on five plausible tab-strip markups:

| markup | trafilatura | `html_fragment.to_markdown` |
|---|---|---|
| `<div role=tablist><button aria-controls>` | **dropped** | kept |
| plain `<div>`s | **dropped** | kept |
| `<ul><li>` | kept | kept |
| `<a href="#qa">` | **dropped** | kept |
| `<h2>` per tab | kept | kept |

`TIER_ORDER = ("site_handler", "raw", "jina")`; there is no Hepsiburada handler,
and an SSR marketplace page clears the `raw` gate — so **trafilatura is the
converter that actually ran**, and the evidence was gone before extraction. A
detector over `content_md` would have been reading a body from which the signal
had already been removed.

`fc.body` retains raw HTML on `raw`, `browser`, `browser_robust`, `archive`,
`site_handler`, and `zyte`. On `jina` and `firecrawl` the body *is* markdown —
those tiers get reduced recall, declared in the spec rather than compensated by
a looser textual heuristic (see D4).

**Rejected: a DOM inventory emitted by the browser tier.** Highest fidelity, but
`RenderedPage` is a shelf type — a field there means a shelf change plus a tag
bump — and it covers 2 of 8 tiers, not including the tier that actually served
this page. `selectolax` is already a top-level dependency, so reading `fc.body`
buys the same DOM precision with none of that cost.

## D2 — The detector is recall-oriented; the extractor judges relevance

**Decision:** detection is deliberately generous; the extractor selects which
gate blocks the answer.

The naive text shape `label + number` is unusable on its own. Generated against
the same converter path, all of these render identically:

```
[Sepet3](…)  [Bildirimler12](…)     cart / notification badges
Değerlendirme Puanı 4,5             rating
Fiyat 1.299,00 TL                   price
Sayfa 1 / 7                         pager
Soru Cevap4                         ← the true positive
```

Precision could come from a query-relevance conjunct — except it cannot, here:

```
query: "seller Q&A questions and answers"
label: "Soru Cevap"
token overlap via _normalize_tokens:  ZERO
```

The motivating case is cross-language, and a deterministic overlap test fails on
exactly the case that motivated the work.

**So the axes are split.** The detector supplies grounded candidates; the model
— which reads the question and bridges languages natively — picks. Precision is
not the detector's job, which is what makes generous DOM matching safe.

This is not ADR-0006's declined `answerable: false`. That was a model
*self-assessment* of answerability in the abstract, declined over router-JSON
wobble risk. This is **selection from a server-supplied closed set**, the exact
mechanism page links already use under ADR-0013: the server digests candidates,
the model picks a handle, the server maps it back. The model can no more invent
a section than it can invent a URL.

**Rejected: extractor-only detection (no DOM phase).** Downstream of the loss —
the model reads the candidate menu, and on the trafilatura path the tab strip is
not in it. A prompt field alone would fix only the jina/firecrawl population.

**Rejected: deterministic-only detection (no model step).** Either fires on
every rich commerce page, or never fires cross-language. Both useless.

## D3 — DOM predicate

Structural, not textual. A candidate gate requires:

- the label sits in a `role="tab"` / `aria-controls` / `aria-expanded="false"`
  element, or a `<summary>` inside a `<details>` without `open`; **and**
- the referenced panel is absent from the DOM, or present and empty.

Plus one positional exclusion: anything the extractor classified as a `role="nav"`
region is dropped — chrome-region counts (cart, notifications) are the largest
false-positive class and they all live there.

Prices, ratings and pagers fail the predicate outright: none is a disclosure
control.

**Known miss:** a site rendering tab labels as `<h2>`/`<li>` with no ARIA gives
the predicate nothing to key on. Accepted — see D4.

**Known correct decline:** a site that renders every panel and hides them with
CSS has a present, non-empty panel, so the predicate declines. That is right;
the content is in the body and the extractor can answer from it.

## D4 — Coverage limits are declared, never papered over

Two populations get reduced recall: markdown-only tiers (`jina`, `firecrawl`),
and ARIA-less tab markup. Both are stated in the spec as accepted limits.

The alternative — a loose textual fallback — would manufacture gates a2web
cannot evidence, which is the same overclaim in the opposite direction from the
defect being fixed. A missed gate degrades to today's behavior; a fabricated gate
sends the caller to a browser for nothing.

## D5 — Placement

A new pure phase in `fetcher/sufficiency/`, mirroring `_phase_listing_completeness`,
writing a typed field on `FetchContext` (never a `dict[str, Any]` bag).

It must be invoked from **both** call sites the listing phase uses —
`comprehension/extract.py` and `retrieval/escalate/seam.py` — with a **symmetric
clear**, so that a later rung which does expand the section retracts the signal
rather than leaving it stale. The listing phase's own clear
(`sufficiency/completeness.py`) is the pattern.

Hint emission and the confidence cap live in `build_ask_response` alongside
`query_title_mismatch`, which is the closest existing idiom: a deterministic,
query-conditioned check that emits an evidence hint and caps confidence.

## D6 — Evidence hint, enforcement cap

The hint carries the evidence; the confidence cap does the enforcement. This is
stated precedent — `served_url_differs_hint`: *"The confidence cap this hint
travels with does the enforcement; this hint carries the evidence."*

Consequence: severity does **not** have to carry the weight of the gap. That is
what allows `warning` rather than `critical`, keeping the `try_user_browser`
klaxon meaning exactly one thing (the URL was not retrieved at all).

Ladder note: `warning` is declared as "unverified", and this case is verified —
the page states the count and the cause is known. But `warning` already carries
certain-but-partial loss in practice (`section_unretrieved`, `index_lost`), and
`info` is dropped from the wire entirely, which would under-warn a total miss of
the asked-for content. The honest reading is that the ladder has no rung for
*verified AND must-act*; that gap is filed separately as an ADR-0017 amendment
rather than resolved by inflating this hint.

## D7 — Remediation is deferred, and separable by construction

There is no click rung to escalate to, so the flow terminates in a hint. When a
shelf backend gains an expand capability, the same detector feeds it and the hint
becomes the fallback for when it fails. Detection and remediation are separate
from day one, so nothing here needs unwinding later.

Remediation, when it comes, is the third member of the post-extraction
completeness-escalation family (obstacle render, listing render, this) and
belongs in the deferred `single-source-escalation-policy` consolidation, not in a
fourth bespoke phase.

## D8 — What the caller sees

```json
{"confidence":"medium",
 "answer":"The page's Q&A section (\"Soru Cevap\") was NOT retrieved. The page itself states it holds 4 entries, but the content loads only after an in-page click and has no separate URL. Treat the questions as unknown, not absent.",
 "title":"Carraro Gravel G2 …",
 "published":"2025-05-26",
 "operator_hints":[
   {"code":"interaction_required",
    "message":"The section you asked about — \"Soru Cevap\", which the page states holds 4 entries — exists but was NOT retrieved: it loads only after an in-page click and has NO separate URL. Do not read this as the source having no Q&A. Re-querying this URL will return the same result.",
    "fix":"Open the URL in a real-browser tool, click \"Soru Cevap\", and read the section — or tell the user this section could not be retrieved.",
    "severity":"warning"}],
 "also_here":["product specs","price, campaigns","return policy"]}
```

Verified against the real serializer: `status`, `tier` and `retrieval_incomplete`
all prune. `content_md` stays withheld — `force_attach` exists so *"the blind
caller is not left with nothing"*, and a live directive is not nothing.

`also_here` deliberately does **not** list the gated section: that field promises
"re-query this URL and you will get it", which would be false here.

For a question the gate does not block, the envelope is byte-identical to
today's.

## D9 — Why no new envelope field

Weighed and rejected; recorded in ADR-0020. The short form: on a non-blocking
query the field would ship with no hint and nothing the caller can act on, which
fails the repo's own caller-actionability test for envelope width. A count earns
a field when it drives a decision — `items_total` gates a scroll render; this one
gates nothing, because no click rung exists. Revisit when one does.

## Open items carried out of this change

- A general `query_unanswered` flag. Wanted, but a flag is only as good as its
  negative: set from one detector, `false` would assert a coverage guarantee
  a2web has not verified. Needs a producer census (ADR-0009 §46).
- The ADR-0017 severity ladder's missing *verified AND must-act* rung (D6).
- `FetchStatus.partial` — declared on the wire contract, produced nowhere.
- `reddit_forbidden_try_archive` / `reddit_deleted_try_archive` ship at `info`,
  whose severity key is dropped from the wire; verify the terminal path escalates
  when the suggested archive fallback also fails.
- `hepsiburada.com` absent from `_JS_HEAVY_HOSTS_SEED` while `trendyol.com` and
  `aliexpress.com` are present.
