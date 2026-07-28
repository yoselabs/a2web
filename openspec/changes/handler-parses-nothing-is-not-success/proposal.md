## Why

**A site handler whose parser matched nothing returns `Verdict.ok`.**
`handlers/arxiv.py::_fetch_listing` parses a listing into entries, gets zero,
and renders that as a confident `## Papers (0)` with `verdict=Verdict.ok`. The
parse result is never consulted before declaring success.

The instance, measured on the live page 2026-07-28:

```
ArxivHandler.fetch("https://arxiv.org/list/cs.CL/recent")
  verdict     ok
  next_links  0
  content_md  40 chars   "# arXiv · cs.CL · recent … ## Papers (0)"

_LIST_ABS_RE       0 matches     tolerant equivalent   50
_LIST_TITLE_RE     0 matches
_LIST_AUTHORS_RE   0 matches
```

All three patterns require double-quoted attributes and `href="`. arXiv serves
single quotes and a space before the `=` — and this is the second-order point:
**the parse is a regex over HTML at all**, so every one of those is a break
waiting to happen:

```html
<a href ="/abs/2607.22529" title="Abstract" …>
    arXiv:2607.22529
  </a>
<div class='list-title mathjax'><span class='descriptor'>Title:</span>
```

**The rot is the instance; the ok-with-nothing is the defect.** A handler that
reported failure when its parser matched nothing would have surfaced this the
day arXiv changed its markup. Instead the handler has been silently
contributing nothing, the gate has been returning `length_floor` on its 40-char
output, and every arXiv listing fetch has been paying a wasted handler dispatch
before escalating to a browser that then re-derives worse results.

**On arXiv the harm is partly masked, and that is luck.** 40 chars trips the
500-char length floor, so the caller gets a browser render rather than a
confident empty. A handler rendering a longer shell around zero items would
clear the floor and the caller WOULD receive `## Papers (0)` as a successful
answer — a silent miss (ADR-0009) dressed as a complete one. The masking is a
property of this handler's terse template, not of the design.

**The class is probably not confined to arXiv.** A static survey of the nine
handlers finds no zero-parse guard in seven of them. That is a grep, not a
proof — some handlers return API objects where a parse count is not the right
signal — so this change audits each rather than assuming.

Found while chasing why `listing-answer-always-leaves-an-index` stays
`unscored`. It is the fourth distinct blocker on that one corpus case, and the
first that is a plain bug rather than a design boundary.

## What Changes

- **A shared `_common.py` helper turns a zero-unit parse into a non-`ok`
  verdict**, so the check lives beside `empty_result` and `map_non_ok` rather
  than being re-derived per handler.
- **Handlers whose success is defined by a parse count adopt it.** Which ones
  those are is task 1's audit, not an assumption in this proposal.
- **arXiv's listing parse moves from regex to selectolax.** Raised in review:
  a tolerant regex is not the fix, it just relocates the rot — quote style,
  attribute order and whitespace all still break it, and the next markup change
  breaks it again. selectolax is already a direct dependency and
  `handlers/_reddit_html.py` already parses with it, so this is adopting an
  existing in-package pattern, not introducing a parser.

  Verified on the live page: `dl#articles` → `zip(dt, dd)` yields aligned
  pairs, with titles, authors and abs ids read from the DOM. It is also less
  code: the regex version hand-rolls document-order slicing between anchor
  matches to pair each id with its title, which `zip(dt, dd)` expresses
  directly.

  The justification is **robustness and scoping, NOT accuracy.** A draft of
  this proposal claimed selectolax was more accurate because it found 47 where
  a tolerant regex found 50. That was wrong, and the review caught it: the
  page renders a variable number of day-sections, and the 50-reading was a
  two-section render (`Mon 27 Jul: showing 47 of 47` + `Fri 24 Jul: showing
  first 3 of 110`). 47 + 3 = 50, and a DOM anchor query agreed at 50 on that
  same render. The regex was counting correctly; I compared two different
  renders of a page that varies between requests.
- **A live-probe guard** asserts the arXiv listing handler yields entries
  against a recorded fixture of the CURRENT markup, so the next rot fails a test
  instead of degrading a tier. The fixture is a real captured page, not a
  hand-written approximation — a hand-written fixture would encode the markup I
  believe arXiv serves, which is exactly the belief that was wrong.
- **NOT** a change to the gate, the tier order, or escalation. The gate did its
  job here; it is the only reason this was survivable.
- **NOT** a claim that this makes `listing-answer-always-leaves-an-index`
  scored. It removes one of at least four blockers on that case. Whether it is
  the last one is a measurement, and this change's own evidence task treats a
  non-move as information rather than failure — three consecutive changes have
  now been written against that case and none moved it.

## Capabilities

### Modified Capabilities

- `site-handlers`: nothing states that a handler must not report success on a
  parse that produced nothing. Gains that requirement, plus the narrower one
  that a handler's rendered output must not assert a count it did not observe.
- `handler-live-probe`: the existing live-probe capability covers handler
  reachability. Gains a requirement that a handler is probed for YIELD, not just
  for a non-error response — a handler returning `ok` with zero units is exactly
  what a reachability probe cannot see.

## Impact

- `src/a2web/handlers/_common.py`: the shared zero-parse helper.
- `src/a2web/handlers/arxiv.py`: `_fetch_listing`'s verdict, and the three
  listing regexes — deleted in favour of a selectolax DOM walk.
- **Ten handler files call `re.compile`.** How many of those run against
  MARKUP (in scope for later conversion) versus URLs / JSON / free text (where
  regex is correct) is task 1.2's audit, not a number this proposal asserts.
  This change converts ONE and states the pattern.
- `src/a2web/handlers/*.py`: whichever the audit shows have the same hole.
- `tests/capabilities/site_handlers/`: the fixture-backed yield guard.
- **Behaviour change for callers**: an arXiv listing fetch begins returning the
  handler's parsed index (47 entries in the observed render, with titles, authors and abs links) instead
  of escalating to a browser that produces neither headings nor a structured
  index. Fewer browser dispatches, better content, and `next_links` populated
  from a natively-known source rather than inferred.
- **A handler that has been silently dead becomes live**, which will change
  output on every arXiv listing URL in the corpus. That is the point, and it
  means the arXiv cells' numbers before and after are not comparable as a
  regression check.

---

## WHAT ACTUALLY SHIPPED (2026-07-28) — read this first

This proposal was written before the spike loop and is **wrong in scope, design
and claim**. It is kept as the record of what was believed at the time; the
delivered change differs on every axis. Corrections, in the order the spikes
found them:

1. **Scope.** "Audit the nine handlers" is DONE, not pending — and the answer is
   two. Live-probing all nine found exactly two dead parsers, and excluding
   named-group syntax there are exactly four markup regexes in the package,
   both files being the two dead ones. 100% of markup regexes were broken;
   the class is enumerated, not sampled.

2. **A second instance, with a DIFFERENT shape.** `wikipedia._wikilink_candidates`
   returned 0 against 1066 `rel="mw:WikiLink"` anchors. Its CONTENT parse is
   fine, so this proposal's "zero parse → non-`ok` verdict" cannot fire on it,
   and forcing it would send a healthy 49 KB article to a browser for nothing.
   Two shapes, two mechanisms.

3. **The fix is a shelf package, not a local helper.** Raised in review:
   "shouldn't we abstract things away, or propose to shelf". Promoted as
   `dom-schema-v0.1.0` — declared CSS extraction with a three-way yield verdict.
   A two-level `Schema` (container + row) makes `ROT` separable from `EMPTY`;
   a flat selector cannot. EVOLVE of `record-mine` was tested and rejected
   (handed arXiv's `<dl>` alone it still returns `None`; and inference vs
   declaration fails monotonicity in the removal direction).

4. **The funnel guard cannot classify pattern text.** Attempted and it failed
   both ways — named groups read as markup, and `listing_oracle`'s `rel\s*=`
   was missed because the target is itself a regex. The shipped rule is
   structural: in `handlers/`, a `re.compile` pattern must be an anchored URL
   path.

5. **The claim was too cautious.** This proposal said it does NOT claim the
   corpus case. It does: `listing-answer-always-leaves-an-index` moved
   `unscored → scored` at 4 and 5 (`eval/runs/post-dom-schema`), after
   defeating three consecutive changes.

6. **`_render_listing`'s "Papers (0)" is gone**, but the deeper reason is the
   verdict: a `ROT` parse now returns non-`ok` and the cascade continues.

Not shipped and correctly out of scope: `reddit-listing` (handler blocked →
zyte wins → zyte carries no candidates — an unrelated defect), and the
wikipedia yield guard, which needs the probe change because its container is
`<body>` and therefore always matches.
