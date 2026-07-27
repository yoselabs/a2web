## Context

Fourth blocker on one corpus case, and the first that is a plain bug. The three
before it were design boundaries (a dropped field, an over-scoped skip, a
four-way duplicated install). This one is a handler that has been silently dead.

```
ArxivHandler.fetch("https://arxiv.org/list/cs.CL/recent")   2026-07-28
  verdict          Verdict.ok        ← the defect
  next_links       0
  content_md       40 chars          "# arXiv · cs.CL · recent … ## Papers (0)"

  _LIST_ABS_RE       0 matches       (selectolax on the same render: 47)
  _LIST_TITLE_RE     0 matches
  _LIST_AUTHORS_RE   0 matches
```

Downstream, that 40-char body trips the 500-char length floor, the gate says
`length_floor`, the browser escalates, and the browser's `TierResult` replaces
the handler's. So the visible symptom for three rounds of investigation was
"arXiv is a browser page with no structured index" — when it is a handler page
whose handler stopped working.

**A methodological note, because it is the fourth time.** The previous round
filed the opposite finding — "the handler builds a correct index and the
escalation discards it" — from reading that `_parse_listing_entries` and
`_listing_candidates` exist and inferring they work. Running the handler took
one command and inverted the conclusion. Every wrong diagnosis in this
investigation has the same shape: a read substituted for a run.

## Goals / Non-Goals

**Goals**

- A handler that parsed nothing cannot report success.
- arXiv listings parse from the DOM, so quote style, attribute order and
  whitespace stop being failure modes.
- The next rot fails a test rather than degrading a tier.

**Non-Goals**

- Converting the other regex-against-markup handler sites. Ten handler files call
  `re.compile`; how many run over markup rather than URLs / JSON / free text is
  the audit's answer, not an assumption. Named, scoped out — see D4.
- Any change to the gate, tier order, or escalation. The gate is the only reason
  this was survivable rather than a silent miss.
- Making `listing-answer-always-leaves-an-index` scored. This removes one of at
  least four blockers. See D5.

## Decisions

### D1 — The verdict guard first, the parser second

Both halves ship, in that order, and the order is the argument. Fixing the
parser makes arXiv work today. Fixing the verdict makes the NEXT breakage
visible. Only one of those is a fix for the defect; the other is a fix for the
instance.

Concretely: `_fetch_listing` consults its parse result before choosing a
verdict, via a helper beside the existing `empty_result` / `map_non_ok` in
`handlers/_common.py`. It lives there rather than inline because the audit (D4)
may find siblings, and a second inline copy is how the four-way install
duplication in the previous change happened.

What verdict a zero-parse yields is deliberately NOT `Verdict.ok`-with-a-hint.
A handler that matched nothing has no evidence about the page — it does not know
whether the listing is empty or its selectors are stale, and those are the two
sides of the empty-vs-wall invariant. The honest verdict is the one that lets
the cascade try something else, which is what happens today by accident via the
length floor. This makes it happen on purpose, and for handlers whose template
is verbose enough to clear the floor, it makes it happen at all.

### D2 — selectolax, not a more tolerant regex

*(Raised in review: "probably regex ain't the best... maybe we need lxml or
parse or query or something even better?" — correct, and it changed this
decision. The draft this replaces made the three patterns quote- and
whitespace-tolerant.)*

A tolerant regex relocates the rot. It survives the single-quote change that
broke it this time and breaks on the next attribute reorder, the next nested
tag, the next stray whitespace. The failure mode is unchanged: silent zero
matches.

selectolax is already a direct dependency (`pyproject.toml`), already used by
`link_digest.py`, and — the part that settles it — already used by
`handlers/_reddit_html.py`. This is adopting an in-package pattern, not
introducing a parser, so it needs no dependency decision and no shelf promotion.

Verified on the live page:

```python
tree.css_first("dl#articles")            # found
zip(dl.css("dt"), dl.css("dd"))          # 47 pairs
dt.css_first("a[title='Abstract']")      # → /abs/2607.22529
dd.css_first("div.list-title").text()    # → "Title: Skill Self-Play: …"
dd.css_first("div.list-authors").text()  # → "Authors: Siyuan Huang, …"
```

Two properties:

1. **Structurally scoped.** `dl#articles` means anchors elsewhere on the page
   cannot leak in, and `zip(dt, dd)` is alignment the markup already asserts. A
   regex over the whole document has no such notion — it recovers the pairing by
   slicing between anchor matches and hoping document order holds.
2. **Less code.** That slicing — `html[match.end() : next_match.start()]` — is
   what `zip(dt, dd)` replaces.

**NOT accuracy. A draft of this decision claimed it was, and the review found
the claim false.** It read: selectolax finds 47 where the tolerant regex finds
50, and 47 is the count the page advertises, so the regex was matching stray
cross-list anchors. Every part of that is wrong. The page renders a VARIABLE
number of day-sections; the 50-reading came from a two-section render:

    Mon, 27 Jul 2026 (showing 47 of 47 entries)
    Fri, 24 Jul 2026 (showing first 3 of 110 entries)     47 + 3 = 50

and a DOM anchor query returned 50 on that same render. The regex counted
correctly. I compared two different renders of a page that varies between
requests and read the difference as a defect in the tool I was replacing.

This matters beyond the correction, because the false claim had already been
promoted into a test design: the non-vacuity floor was specified as "the count
the page advertises for itself". There is no such count. There are per-section
counts, a `showing first N of M` partial marker, and a `Total of 408 entries`
footer. A guard written to that spec would have been unimplementable, or worse,
implemented against one section and passing while the parser dropped another.

Fifth wrong claim in this investigation, and the fourth of the same shape: a
single observation generalised without a second look.

*Alternative considered:* `html_fragment` (the shelf package, lxml-based). It
exposes `to_markdown` / `to_text` / `unescape`, which is a rendering surface,
not a query surface — it has no CSS selection. Wrong tool for "find the entries
in this listing", right tool for "turn this fragment into text". Not adopted.

*Alternative rejected:* route this through `record_mine`. It is the repo's
structural record detector and it would be the elegant answer, but it returns
`None` on this page — a `<dl>/<dt>/<dd>` listing is not the repeated-sibling
card grid it detects. That is a real `record_mine` gap and a candidate for a
shelf promotion later; it is not this change.

### D3 — The guard's fixture is a captured page, never a hand-written one

The yield guard asserts the handler returns entries commensurate with a known
count. Its fixture is a real captured arXiv listing, checked in.

The count comes from the CAPTURE — `dt`/`dd` pairs counted once, by hand, in the
committed file — and never from the page's self-description. Those are not the
same number and the page has several of them (per-section `showing N of M`, a
`showing first N of M` partial marker, `Total of 408 entries`).

**This is not a hypothetical, and it is not an argument. It is already true in
this repo.** `tests/capabilities/site_handlers/test_handlers_arxiv.py::test_arxiv_listing_html_parser_extracts_entries`
is GREEN today, against a hand-written fixture:

```html
fixture     <a href="/abs/2401.0001">arXiv:2401.0001</a>
            <div class="list-title mathjax"><span class="descriptor">Title:</span> …

live page   <a href ="/abs/2607.22529" title="Abstract" …>
                arXiv:2607.22529
              </a>
            <div class='list-title mathjax'><span class='descriptor'>Title:</span>
```

The fixture was written from the same mental model as the regex — double quotes,
no space before `=`, anchor text flush against the tags. So it cannot fail when
the regex is wrong about arXiv; it can only confirm that the regex agrees with
itself. A passing test and a dead handler, side by side, for however long this
has been rotten.

That is oracle endogeneity exactly: a double cannot witness a change to the
thing it was copied from. The fixture is not a bad test of the parser — it is
not a test of arXiv at all, and arXiv is the thing that changed.

The count is the non-vacuity floor, per the repo's standing rule for structural
guards: "returns something" passes on one stray entry.

**A synthetic fixture remains legitimate for testing the CAP**, and the existing
15-entries→10-candidates scenario keeps one. The rule is about what may serve as
the ORACLE for "does this parser match arXiv" — a hand-written page cannot. A
hand-written page controlling an entry count to exercise a truncation rule is a
different job, and the two must not be collapsed: deleting the synthetic fixture
would lose cap coverage, keeping it as the parse oracle is the defect.

### D4 — Ten other regex-over-markup sites are named, not converted

`re.compile` appears in ten handler files. How many of those run against MARKUP
is not known — some patterns run over JSON, URLs or free text, where regex is
correct. Converting them all would be a refactor justified by a pattern rather
than by a defect, and the pattern is currently a `grep -l` count.

The audit in task 1 establishes, per handler, whether its success is defined by
a parse count — which is the question the verdict guard needs answered anyway.
Conversion of the parsers is a follow-up scoped by that audit's output. Named in
BACKLOG so the pattern is not lost, which is the failure mode the trafilatura
funnel was built to prevent.

### D5 — This change does not claim the corpus case

`listing-answer-always-leaves-an-index` has now defeated three consecutive
changes, each of which fixed something real. This is the fourth blocker found on
it and there is no basis for believing it is the last.

So the evidence task measures and reports, and a non-move is recorded as
information rather than as failure. What this change IS accountable for is
narrow and checkable: the handler yields 47 entries where it yielded 0, and a
zero-parse no longer reports success. Whether that is sufficient for the cell is
a separate question with a separate answer.

## Risks / Trade-offs

- **A silently dead handler becomes live**, changing output on every arXiv
  listing URL. Before/after numbers on those cells are not comparable as a
  regression check — this is new behaviour, not changed behaviour.
- **The handler now wins where the browser used to.** Handler output is terser
  and structured; browser output is prose-shaped with 484 links. If the
  extraction quality on arXiv listings drops, that is the trade and the bench
  will show it. Cheaper and faster is not automatically better.
- **selectolax couples the handler to arXiv's DOM structure** (`dl#articles`,
  `div.list-title`) rather than to its byte patterns. That is a better coupling,
  not the absence of one — a redesign still breaks it. The difference is that
  the guard now catches it.
- **The verdict guard may make handlers fail where they used to quietly
  degrade.** That is the intent, but a handler that returns non-`ok` on a
  genuinely empty listing sends the cascade off to a browser for nothing. The
  audit must distinguish "parsed nothing" from "parsed an empty page", and where
  it cannot, this change does not apply the guard.

## Open Questions

- **Do the other eight handlers have this hole?** Static survey says seven lack
  an obvious zero-parse guard, but that is a grep. The audit answers it; the
  answer may be that most are API handlers where the count is not the signal.
- **Should `record_mine` learn `<dl>/<dt>/<dd>` listings?** It returns `None`
  here, which is why the digest gate declined on this page even with 484 links
  available. A definition-list listing is a real and common shape. Shelf
  promotion candidate, needs a second example first.
- **Is a live-probe capability the right home for a yield assertion?** The
  existing `handler-live-probe` checks reachability, which structurally cannot
  see this defect. Extending it means live network in a suite that is otherwise
  offline; the fixture guard is the offline half. Whether both are needed is
  worth deciding once the audit shows how many handlers are affected.
