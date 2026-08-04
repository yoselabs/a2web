# Which invariants can the corpora actually catch?

`close-guards-that-read-green` §6.6. Re-measured 2026-08-02, after §6.2 (one
contract vocabulary, two harnesses) and §6.4 (the criteria walk) landed.

The question is deliberately narrow: **if this invariant broke, would a cell go
red?** Not "is it tested" — most of these have unit tests. The corpora exist to
witness the invariants end-to-end, over real pages or frozen bytes, where a unit
test's hand-built fixture cannot reach.

## What counts as a catching cell

A cell catches an invariant only if it can FAIL when the invariant breaks.
Three tiers, and the distinction is the whole point of this document:

| tier | mechanism | can it fail? |
|---|---|---|
| **D** deterministic | a `contract:` key (live bench) or a blessed `contract.json` key (offline replay) | yes, definitively |
| **J** judged | a `criteria` line the judge can evaluate from the ANSWER TEXT alone | yes, probabilistically |
| **∅** unreadable | a `criteria` line whose subject the judge cannot see | **no, ever** |

The ∅ tier is not a rhetorical category. `JUDGE_V1` has three slots — `{ask}`,
`{content}` (the criteria list), `{answer}` — and **the fetched page is not one
of them.** Every "does not fabricate X" criterion is addressed to a reader with
no ground truth. It reads as coverage and provides none. §6.4 kept these rather
than deleting them, precisely so this table can count them.

## The map

Twelve invariants, as enumerated by the 2026-07-31 structural scan. Cells are
named; a count with no names would be the same unfalsifiable shape this document
exists to expose.

| # | invariant | D | J | ∅ | catching cells |
|---|---|---|---|---|---|
| 1 | **ADR-0009** wire half (failed ⇒ `retrieval_incomplete` + `narrative` + diagnostics + critical hint) | **4** | 3 | 2 | offline `zoro-datadome-bot-wall` (all four signals, as of this session); bench `datadome-wall-commerce` (`status`/`retrieval_incomplete`/`narrative_present`/`answer_present` + `hint_severity`) |
| 2 | **ADR-0012** never manufacture a selection | 0 | **4** | 0 | `gh-trending-best`, `trendyol-listing-which-best`, `reddit-iem-compare`, `v2ex-topic` — all judged, and legitimately so: neutrality is a property of prose |
| 3 | **ADR-0013** closed-set `{{n}}` handles | 0 | 0 | **2** | still none in either corpus — a handle is consumed before the envelope exists, so no cell can see one. Enforced by `tests/capabilities/link_affordances/test_rehydration_seam.py`, which since 2026-08-03 also covers the NO-digest branch (see below) |
| 4 | **ADR-0014** every URL traceable to the page | **7** | 0 | 4 | `answer_urls_traceable` on `pypi-httpx` (the historical specimen), `other-pages-carries-the-real-kind-and-anchor`, `json-ld-itemlist-leaves-an-index`, `hepsiburada-reviews-drilldown-on-page`, `contact-page-channels`, `discourse-topic-list`, `walled-listing-recovered-via-archive`. **Was zero when this table was first written, later the same day — see below.** |
| 5 | **ADR-0015** withheld body leaves an index | **7** | 2 | 0 | `listing-answer-always-leaves-an-index`, `discourse-topic-list`, `json-ld-itemlist-leaves-an-index` (×3 keys), `wikipedia-narrow-ask-indexes`, `github-repo-issues-affordance`, `other-pages-carries-the-real-kind-and-anchor`, `walled-listing-recovered-via-archive` |
| 6 | **ADR-0016** never bill the metered API | n/a | n/a | n/a | not a corpus question — enforced before the call by `anyllm.cost` (`CostViolation`), which is the right layer |
| 7 | **ADR-0017** effort/confidence ∝ evidence | **1** | 2 | 1 | `dead-product-url-fat-404` (`confidence_max`, `content_not_found`, no `try_user_browser`) — one cell, and it arrived this session |
| 8 | empty-vs-wall discrimination | **2** | 5 | 2 | `trendyol-200-soft-404-empty-results` + `incehesap-404-dead-search-url` (both: the klaxon must NOT fire). The `ok`-promotion side is still judged |
| 9 | tier-truthfulness (never launder a 404 into `ok`) | **2** | 1 | 1 | `dead-product-url-fat-404` (`status: failed` + `content_not_found`), `tiny-complete-page` (the inverse: a small page is not a miss) |
| 10 | listing `options` shape | **2** | 2 | 0 | `json-ld-itemlist-leaves-an-index` (`options_min`), `hepsiburada-product-no-footer-options` (`options_max: 0`) |
| 11 | never cache below the gate | 0 | 0 | 0 | **still none in any corpus** — neither harness observes the cache, and no corpus cell can (see below). Enforced instead by `tests/capabilities/tier_pipeline/test_cache_write_gate.py` since 2026-08-03 |
| 12 | the planner's routing decisions | **6** | 0 | 0 | six offline baselines pin `steps`; two did not until this session |

## What moved, and what did not

**Before this change: 9 of 12 had zero catching cells. Now 2 do** — #3
(ADR-0013) and #11 (never-cache-below-the-gate). #2 is judged-only by design
rather than by neglect. #4 was a third until `answer_urls_traceable` closed it
hours after this table was first written; the before/after is left visible
because the reason it looked unclosable is the interesting part.

### #11 has no corpus cell because it cannot have one

Added 2026-08-03. A cached block page produces a perfectly normal-looking
response *on the fetch that stored it*; the harm appears only on the NEXT
fetch of the same URL, served from the poisoned row. Both harnesses fetch each
case once and read one envelope, so no cell they could contain would catch it.
The "∅" was therefore never asking for a corpus case — it was asking for
enforcement somewhere, and the gate is a pure boolean over context state, which
is a unit test's shape rather than a corpus cell's.

Checked while closing it: **no test in the repository named `_phase_cache_write`
at all.** Zero corpus cells and zero unit tests, for a rule on CLAUDE.md's Never
list, whose failure mode is worse than an ordinary miss — a block page in the
cache is a silent miss that REPEATS for the whole TTL with no network request to
notice it.

The gate is a six-term conjunction, so each term is now tested as a term, plus
the positive case (without which every "must not write" assertion is vacuous —
a gate that never writes would pass them all). Mutation-verified by deleting
each clause in turn: every deletion turns the file red, and deleting the
gate-passed clause fails eight.

The clause worth naming is the promotions'. `_phase_empty_promotion` and
`_phase_complete_small_page_promotion` deliberately leave the verdict at
`length_floor` **so that this gate declines them** — two comments say so, and
nothing enforced it. "Fixing" that verdict to `ok` at the promotion site is a
one-line change that looks obviously right in isolation and would start
persisting wire-only promotions, which is the repeating silent miss the
empty-vs-wall design explicitly warns about.

The four that gained deterministic cells (#1, #5, #7, #9) plus #10 and #12 are
the §6.2/§6.4 return. #5 went from zero to seven, which is the single largest
move: ADR-0015 is an invariant about a STRUCTURE (`other_pages` / `options` /
`also_here` non-empty), and a structure is exactly what a deterministic key can
assert and a prose judge cannot.

### #4 (ADR-0014) was the honest zero, and then it was closed

As first measured: seven criteria, six cases, not one able to fail. The
invariant is *"every URL a2web emits is traceable to the fetched page"* —
checkable only by a reader holding both the emitted URLs and the page. No
harness passed the page to anything.

That reads as §6.1's scope, and §6.1 is open for a reason worth restating:
passing the page to the QUALITY judge changes every quality score and breaks
comparability with the current baseline. **But ADR-0014 never needed a judge.**
The ADR's own wording is a membership test — *"a URL literally present in the
page content"* — so the check is: does each URL in the answer appear in the body
we retrieved, in the index we emitted, or as the page's own address? Closed the
same day as `answer_urls_traceable`, on seven cases.

Scope, stated so nobody reads more into it than it does:

- It checks the **answer prose**, which is the hole the ADR names. `other_pages`
  is already structurally safe — the model emits `{{n}}` handles and closed-set
  rehydration drops any the digest does not know.
- It is **vacuously true on an answer citing nothing**, so it is pinned on cases
  whose answers are expected to carry links, `pypi-httpx` first: that exact cell
  is where the memory-URL was measured (`python-httpx.org`, written from
  training rather than read from an anchor).
- **Known false-positive mode:** an anchor whose href never survives extraction
  into `content_md` reads as untraceable. Acceptable for a bench axis in a way
  it would not be in production — a URL in the answer that is absent from the
  body we captured is worth a look whichever way it resolves. It must not be
  ported into the fetch path as a filter.

### #11 has no cell and no plan

"A block page must never enter the cache" is a first-class Never in CLAUDE.md
with zero corpus coverage in either harness. Neither observes the cache at all,
so this is not a gap to fill with a criterion — it needs a projection field
first. Recorded, not fixed.

### #12 was claimed and was not true

§4.1 recorded the `steps` planner witness as *"blessed on all seven
baselines"* and §6.3 recorded akakce as pinning `retrieval_incomplete` +
`narrative_present`. Measured this session: **two of eight baselines carried
neither `steps` nor the ADR-0009 flags** — including
`zoro-datadome-bot-wall`, the corpus's canonical wall specimen and the one cell
#1 depends on. The bless code was correct; the baselines were never re-blessed
after the case was split. The tasks described the code and not the corpus.

Fixed by one `A2WEB_BLESS_EVAL=1` run, verified by flipping
`retrieval_incomplete` to `false` and confirming the case goes red. But the
lesson is the change's own: **a completed task is a claim about the tree, and a
claim about the tree is checkable.** Nothing here would have failed; the
assertions simply did not exist.

## Method

- D counted from `eval/corpus.yaml`'s `contract:` blocks and
  `eval/corpus/*/*/baseline/contract.json`, both read programmatically.
- J/∅ split by reading each criterion against `JUDGE_V1`'s three slots. A
  criterion naming an envelope field, a page fact, or a run configuration is ∅.
- #6 marked n/a rather than 0: enforcing a spend guard through a benchmark that
  itself spends would be the wrong layer, and `anyllm.cost` already raises
  before the call.


## #3 (ADR-0013) had unit coverage, and a hole in the branch nobody tested

Added 2026-08-03, closing this table's other zero.

Like #11, the "no catching cell" entry was the wrong frame: a `{{n}}` handle is
resolved *before* the envelope is built, so nothing either harness observes
could ever contain one. The invariant lives at the seam, and the seam had tests
— `rehydrate_handle` for `other_pages`, `rehydrate_text` for the answer prose.

What neither covered was the branch where there is **no digest at all**:

```python
fc.extracted_answer = (
    fc.link_digest.rehydrate_text(result.answer) if fc.link_digest else result.answer
)
```

`_build_link_digest` returns `None` for a prose-only article — no links, or no
json_synth/record_synth candidate. The `LINKS IN THE ANSWER` clause that teaches
the model the `{{n}}` convention lives in the BASE prompt and ships on every
extraction, digest or not. So the model was taught the convention, given no link
list, and anything it emitted reached the caller verbatim. Demonstrated:
`"Reviews are on a separate page: {{1}}"` in, byte-identical out.

The comment on that line read *"no-op when no digest was fed"*, which sounds
safe and describes the defect exactly. CLAUDE.md meanwhile claimed the prose is
rehydrated "never leaked" — true only in the branch that had a digest. Both
corrected; the branch now strips.

**The test-shape lesson is the transferable part.** The first three tests
written for this fix all passed with the fix REVERTED, because they exercised
`strip_handles` rather than the line that calls it. Verified by mutation, which
is the only reason it was noticed. A helper proven correct and not proven wired
is this repository's most-repeated failure, and the fix is an end-to-end case
through `fetch()` with a provider that emits a handle — not a contrived double,
since a model doing that is following the instructions it was sent.
