## Context

Three layers had to be peeled before this was diagnosed correctly, and two
confident wrong answers were filed on the way (both recorded in
`eval/findings_2026-07-28.md`). The sequence matters, because each wrong answer
was a reading of prompt text and the right one is a call graph:

```
  "also_here and other_pages are the same thing, confused"     ← no; different
                                                                  page, different cost
  "the four index fields defer to each other, no rule wins"    ← true but not causal
  fc.links is never populated on the pre-rendered path         ← the cause
```

The live call chain, verified by probe and by reading:

```
tier ∈ {browser, jina, zyte, firecrawl, archive} or any of the 9 handlers
  │
  ├─ TierResult.pre_rendered = Rendered(content_md, title, byline, headings)
  │                                       ↑ no links field
  ├─ _phase_extract:  raw_html = fc.body.decode(...)         fetcher.py:1268
  │                   if fc.pre_rendered_payload is not None:
  │                       copy 4 fields; RETURN               fetcher.py:1270-1276
  │                                                              ↑ raw_html is in
  │                                                                hand and dropped
  ├─ fc.links = extract_result.links   NEVER REACHED          fetcher.py:1318
  ├─ _build_link_digest: if not fc.links: return None         fetcher.py:2317
  └─ prompt: "If no '## page links' list is present, OMIT other_pages"
```

And independently, the markdown fallback:

```python
# tiers/browser.py:71
trafilatura.extract(html, url=url, output_format="markdown",
                    include_comments=False, include_tables=True)
                    # include_links defaults to False → every href stripped
```

Probe on `arxiv.org/list/cs.CL/recent` (browser tier, `include_links=True` on the
fetch): 2868 chars of `content_md`, 50 arXiv ids, **0 links, 0 headings, 0
occurrences of `](`**. Nothing to point at, by either mechanism.

## Goals / Non-Goals

**Goals**

- A page's anchors survive retrieval regardless of which tier won.
- `other_pages` becomes reachable on the hard-fetch population.
- The invariant is pinned by a guard that fails when a link-dense page yields no
  links, so this cannot silently regress again.

**Non-Goals**

- Changing the prompt, `RouterPayload`, handle rehydration, or the meaning of
  `other_pages` / `also_here`. All correct; all starved.
- Undoing the `pre_rendered` optimisation. Skipping trafilatura's *content*
  extraction on a tier that already produced markdown is right; losing the
  *anchors* was an unintended side effect of it.
- Fixing the JSON-API handlers (`reddit`, `hn`, …). Separate design, separate
  change — see Open Questions.
- Any change to the measurement layer. `close-silent-eval-loss` surfaced this;
  the two must stay independently verifiable.

## Decisions

### D1 — The real defect is six bypasses of the shelf extractor, not a missing flag

*(This decision replaces an earlier draft that proposed re-parsing the HTML
inside `_phase_extract`. Raised in review: shouldn't the trafilatura call and its
`include_links` be encapsulated in a shelf package? It already is, and finding
that inverted the design.)*

a2web depends on the shelf `content_extract`, and `fetcher.py:27` already imports
it as the canonical extractor:

```python
extract_markdown(html: str, url: str, *, include_links: bool = False) -> ExtractedContent
#   → ExtractedContent(content_md, title, byline, published, headings, links, score)
#   → ExtractedLink(anchor, href, role)
#   → runs off-thread, so async callers never stall on trafilatura
```

It does the same trafilatura extraction, already exposes the `include_links`
flag, already returns structured links and headings, and already owns the
thread-offload chokepoint. **Six sites in a2web call `trafilatura.extract`
directly instead** — `tiers/browser.py`, `tiers/archive.py`,
`handlers/wikipedia.py`, `handlers/reddit.py`, `handlers/twitter.py`. Each
re-derives a subset of what the shelf function returns, and each drops the links
and headings on the floor because a bare `trafilatura.extract` never had them.

So the fix is not "add a flag in two places". It is **delete the hand-rolled
`_to_markdown` copies and call the shelf extractor**, which returns markdown and
links and headings from ONE parse.

*This subsumes the earlier D2* (adding `include_links=True` to two hand-rolled
calls) — there are no hand-rolled calls left to add a flag to.

### D2 — `Rendered` gains `links`, filled by the producer that already has them

Because D1 makes every HTML-serving tier hold an `ExtractedContent` with links in
it, carrying them across the seam is now free. `Rendered` grows a `links` field
alongside the `headings` it already carries — a symmetric addition to an existing
typed field, not a new concept.

*Alternative rejected (this was the earlier D1):* re-run link extraction inside
`_phase_extract` over `fc.body`. It looked attractive because `raw_html` is
already decoded three lines above the early return. But it means **two trafilatura
passes per browser fetch** — once in the tier for markdown, once in the fetcher
for links — over the same bytes. trafilatura is the `asyncio.to_thread` chokepoint
this repo is careful about; paying it twice to recover data the first pass already
computed is the wrong trade. It also leaves the six bypasses in place, so the
next tier author reintroduces the bug.

*Consequence:* tiers whose body is not HTML are still unimproved — jina returns
markdown bytes, the API handlers return JSON. Unchanged from the earlier draft,
still stated in the spec as a known gap, still deferred (Open Questions).

### D3 — The guard asserts a link-dense page yields links, per tier

A fixture with a known anchor count goes through each pre-rendered tier's
installation path; the assertion is that `fc.links` is non-empty and its count is
plausible against the fixture. The count floor is the non-vacuity assertion: a
guard that asserts merely "not empty" passes on a single stray anchor from
boilerplate.

*Not* asserted: which links, or their ranking. That is `link-affordances`
territory and is judged by the bench, not by a unit test.

## Risks / Trade-offs

- **Token cost rises.** `content_md` with inline links is larger, and a populated
  digest adds prompt tokens on pages that previously sent none. The envelope-diet
  work (v0.3) fought hard for those tokens. `make bench` measures it; the token
  axis is one of the four and is free to score.
- **`other_pages` will start firing where it never has**, on the population the
  model has never been exercised against. Quality is unknown — the `next_links`
  axis has exactly one prior observation ever (mean 3.17, 2026-07-28), and none
  of it on browser-served pages. Expect the first numbers to be poor and treat
  them as a baseline, not a regression.
- **D2 may make content worse.** Explicitly gated on measurement, and separable.
- **Off-domain link exposure grows.** More anchors reaching the digest means more
  off-domain candidates. ADR-0014/D11 already requires question-conditioned
  justification for those and the prompt clause is unchanged — but the clause has
  been exercised far less than it is about to be.

## Open Questions

- **The JSON-API handlers.** `reddit` and `hn` know their permalinks natively and
  could populate links with better precision than any HTML parse. Should they
  gain a typed `links` on their `TierResult`, or should `Rendered` grow the field
  after all once there is a second real caller for it? Deferred deliberately:
  deciding it now would be deciding it from one example.
- **jina** returns markdown, not HTML. Its links could be recovered by parsing
  `](url)` out of its own output. Worth doing, but it is a different parser and
  belongs with the handler question.
- **Is `_DIGEST_GATE_SOURCES` still right?** `_build_link_digest` also requires a
  `json_synth`/`record_synth` candidate, so even on the raw tier a prose-shaped
  listing gets no digest. That gate looks deliberate ("prose-only articles skip it
  and pay nothing") and is left alone here — but with D1 landing, it becomes the
  next thing standing between a page and its index. Review it after measuring.
