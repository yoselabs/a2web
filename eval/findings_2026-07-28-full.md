# Findings — full-corpus run, 2026-07-28

Run: `eval/runs/2026-07-28_full` · 114 cells (38 cases x 3 systems) · 743 s ·
provider `claude-code-sdk` (subscription, ADR-0016 — the `$9.11` in the report
is an ESTIMATED token cost, not metered billing) · judge `claude-sonnet-4-6`.

Closes `close-silent-eval-loss` task 8.1b, which had been left open pending a
spend decision.

## Read this before comparing to 2026-07-22

**The corpus grew from 29 cases to 38 between the two runs** (+4 handler-coverage
entries last session, +1 this session, +4 earlier). Cross-run MEANS are therefore
not a regression comparison — the case mix changed underneath them. Per-class and
per-slug numbers are readable; the headline means are not.

| | 2026-07-22 (29) | 2026-07-28 (38) |
|---|---|---|
| webfetch_baseline | 2.03 | 2.27 |
| a2web_detail | 3.07 | 3.29 |
| a2web_extract | 3.38 | 3.41 |

Contract conformance: **38/38 on both a2web systems**.

Standing shape, unchanged and still the product's case: `a2web_extract` beats
WebFetch on quality (+1.14) at comparable envelope cost (+277 tokens), while
`a2web_detail` buys +1.02 quality for +3453 tokens and craters clarity (-2.22).

## What moved

**`reddit-listing` now scores, and scores 5/5.** It was UNSCORED on 2026-07-22
(blocked) and is recorded in BACKLOG as such. Both a2web systems now answer it
at quality 5; WebFetch gets 0. The BACKLOG entry can close.

**`twitter-upstream-walled` scores 4/4.** The expected-red entry is not red:
every nitter instance is walled, but the cascade reaches the tweet via jina.
WebFetch gets 0 (HTTP 404). This is the same result the handler change measured
live, now confirmed by the judge.

**The four handler-coverage entries all score.** `habr-article` 5/5,
`v2ex-topic` 5/5, `discourse-topic-list` 5 (detail) / 3 (extract). The handlers
that had zero coverage now have scored cells.

## The finding: a2web answers a listing-completeness question WORSE than WebFetch

`arxiv-listing-partial` — added THIS session, and the worst cell in the run:

| system | quality | answer |
|---|---|---|
| webfetch_baseline | **5** | reads the raw page, sees the stated total |
| a2web_detail | **1** | |
| a2web_extract | **2** | "The page header states '## Papers (25)', indicating 25 total papers. You are seeing all 25 on this page — no truncation notice or pagination control." |

The page says **"Total of 445 entries"** and renders 50 behind 9 pagination
links. a2web asserted completeness over a 25-item slice of it — a confident
silent miss of exactly the class ADR-0015's index exists to prevent, and the
caller cannot see the body to catch it.

### Causal chain, verified end to end

```
arXiv listing
  └─ handler pre-renders markdown  →  "## Papers (25)", NO total, NO pagination
  └─ pre-rendered ladder runs      →  extract_records(html) returns None
                                       (the <dl>/<dt>/<dd> shape, BACKLOG 7.2)
  └─ fc.record_count stays None
  └─ _maybe_flag_partial_listing() returns at its first line
  └─ listing_oracle() IS NEVER CALLED
  └─ no listing_partial / listing_more hint
  └─ the LLM sees only "Papers (25)" and answers from it
```

Measured directly, not inferred:

```
tier: site_handler:arxiv   status: ok
items_loaded: None  items_total: None  items_more: None   hints: []
content_md 6110 chars — "Total of" present: False | "445" present: False
extract_records(<live arxiv listing html>) -> None
```

### Two separate defects, neither fixed by this session's oracle change

1. **`extract_records` does not recognise `<dl>/<dt>/<dd>`**, so `record_count`
   is None, so the whole partial-listing machinery is disabled on this page.
   This was already in BACKLOG as a shelf-promotion candidate wanting "a second
   example first". It is now LOAD-BEARING, not speculative: it is the reason a
   listing reports 50-of-445 as complete. Upgraded in BACKLOG.

2. **The arXiv handler drops the page's own total and pagination** from its
   rendered markdown. Even with defect 1 fixed, the model reading `content_md`
   has no total to report. A handler that renders a listing should carry the
   listing's stated size.

### What this says about the `listing_oracle` fix committed earlier today

Adding "entries" to the noun list was **necessary and insufficient**. It is
correct — verified live, `listing_oracle` now returns 445 and
`assess(loaded=50, total=445)` is `partial` — but on the arXiv path the function
is never reached, because the gate above it (`record_count is None`) closes
first. The fix pays off for non-handler listings that use the word "entries";
it does nothing for this case.

Worth stating plainly: had this corpus entry not been added the same session the
defect was noticed, the oracle fix would have been recorded as closing a case it
does not close. The corpus entry is what caught it.

## Not established by this run

- **Independence.** Extraction cache was ON (default). Cells may share cached
  extractions with earlier runs.
- **Quality deltas vs 2026-07-22.** Different case mix; see the caveat above.
- **`next_links` coverage.** 14 cells unscored, 10 of them "system produced no
  candidate block" — the ADR-0015 index gap already recorded in BACKLOG
  (`listing-answer-always-leaves-an-index`). Unchanged by this run.
- **2 quality cells lost to a judge parse error** (`int() argument … not
  'list'`) — the judge returned a list where a scalar was expected. Small, but
  it is silent loss of the kind `close-silent-eval-loss` exists to prevent.

## Follow-up, same day: the handler half is fixed

`eval/runs/2026-07-28_arxiv_recheck` — single slug, `--no-extraction-cache`, 26 s.

The arXiv handler now carries the page's advertised total into its rendered
markdown, sourced from `listing_oracle` (not a new regex — `handlers/` may not
carry markup regexes):

    # arXiv · cs.CL · recent
    ## Papers (25 of 445)

    _Showing 25 of 445 entries the page advertises — this is a partial view._

| system | quality before | after |
|---|---|---|
| webfetch_baseline | 5 | 5 |
| a2web_detail | 1 | **5** |
| a2web_extract | 2 | **5** |

Clarity 5 across all three. The extract answer is now:

> "The page advertises 445 total papers in cs.CL (recent), but shows only 25 of
> them. This is a partial view; the remaining 420 papers are not displayed on
> this page."

**This fixes the ANSWER, not the SIGNAL.** Defect 1 (`extract_records` returning
None on `<dl>/<dt>/<dd>`) is untouched, so `record_count` is still None, so
`_maybe_flag_partial_listing` still returns at its first line and NO
`listing_partial` operator hint fires on this page. The model reports the
shortfall in prose because it can finally see it — a machine consumer reading
hints still cannot. That half is shelf work and stays open in BACKLOG.

The single-slug re-bench is a targeted check, not a corpus-wide claim: it says
this cell moved, nothing about the other 37.
