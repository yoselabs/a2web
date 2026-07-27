## Why

**`other_pages` cannot be emitted on any page that was not served by the raw
tier.** Not "tends not to be" — cannot. Every browser, jina, zyte, firecrawl and
archive fetch, and every one of the nine site handlers, installs a
`TierResult.pre_rendered: Rendered(content_md, title, byline, headings)`. That
dataclass has no `links` field, and `_phase_extract` copies those four values and
returns (`fetcher.py:1270-1276`) **before** `fc.links = extract_result.links`
(`fetcher.py:1318`) ever runs. `fc.links` stays empty, `_build_link_digest` bails
on `if not fc.links` (`fetcher.py:2317`), no `## page links` block reaches the
prompt — and the prompt then correctly instructs the model to omit the field:

> *"If no '## page links' list is present, OMIT other_pages — do not invent URLs."*

The model is obeying. ADR-0014's closed-set handle rehydration is intact and
correct throughout. It simply never receives a digest.

**The fallback path is starved too, by a separate defect.** The older mechanism
selects candidates from inline markdown links in the page content
(`link-discovery` spec, "Tier 2"). `tiers/browser.py::_to_markdown` and
`tiers/archive.py::_to_markdown` call `trafilatura.extract(...)` without
`include_links=True`, and trafilatura's default strips every href. Verified
offline on a realistic document: the same HTML yields
`Attention Is All You Need Again` without the flag and
`[Attention Is All You Need Again](https://arxiv.org/abs/2607.1)` with it.

So on a browser-served page there is no digest AND no inline link — nothing
anywhere for the model to point at.

**This breaks ADR-0015 across the entire hard-fetch population**, which is
exactly the population where it matters most: a caller cannot cheaply re-fetch a
page that needed a browser to retrieve, so the index it was promised is the only
affordance it has. Measured, not inferred — `eval/runs/axis-revival-probe`
(2026-07-28): `arxiv.org/list/cs.CL/recent` via browser returned an envelope of
`['answer','confidence','operator_hints','tier']` with 50 arXiv ids in
`content_md`, **0 links, 0 headings, 0 markdown link targets**. `reddit-listing`
via zyte failed the same way. One mechanism, both cells.

## What Changes

- **The pre-rendered path populates `fc.links`** — from the links the producing
  tier now hands over, not from a second parse. This restores the anchors the
  tier already fetched; it does not re-run content extraction or undo the
  trafilatura-skip optimisation that `pre_rendered` exists for.
- **The six direct `trafilatura.extract` callers route through the shelf
  extractor.** `content_extract.extract_markdown(html, url, include_links=True)`
  already returns markdown, links, headings and metadata from one off-thread
  parse. `tiers/browser.py`, `tiers/archive.py`, `handlers/wikipedia.py`,
  `handlers/reddit.py` and `handlers/twitter.py` each re-derive a subset by
  calling trafilatura directly and drop the links on the floor. Delete the
  hand-rolled copies.
- **`Rendered` gains a `links` field**, alongside the `headings` it already
  carries, filled by the producer that now has them in hand.
- **A trafilatura funnel guard**, banning direct `trafilatura` use outside the
  one module allowed to have it. This is the root-cause fix: the canonical
  extractor existed in-repo on the day the first bypass was written
  (`fetcher.py` imported it the same day `tiers/browser.py` went around it), and
  every subsequent promotion moved the canonical copy further up the stack while
  the bypass stayed put. The repo already funnels `json.loads` this way; nothing
  funnels trafilatura, which has the identical shape.
- **A guard pins the invariant that a link-dense page yields links**, regardless
  of which tier served it. Written against a fixture with known anchor count so
  it cannot pass vacuously, and it must be watched failing first.
- **NOT** a change to the prompt, to `RouterPayload`, to handle rehydration, or
  to what `other_pages` means. Those are all correct; they were starved of input.
- **NOT** a fix for handlers whose body is a JSON API payload rather than HTML
  (`reddit`, `hn`, and the rest of the nine). Those know their own permalinks and
  can populate links directly, but that is a per-handler question with its own
  design, and bundling it would hide which fix restored what. Scoped out
  explicitly, and named in the specs as a known remaining gap.

## Capabilities

### Modified Capabilities

- `link-discovery`: its Tier 2 requirement assumes inline markdown links are
  present in the page content. On every pre-rendered tier they are not, and
  nothing detects that. Gains a requirement that link availability is a property
  of the fetch, not of which tier happened to win.
- `link-affordances`: the `other_pages` index is unreachable outside one tier.
  Gains a requirement that the digest is built whenever the retrieved page
  carried anchors, independent of the retrieval path.

## Impact

- `src/a2web/fetcher.py`: `_phase_extract`'s pre-rendered branch (1270-1276) —
  the one early return that drops the anchors while `raw_html` is already decoded
  three lines above it and otherwise unused.
- `src/a2web/tiers/browser.py`, `src/a2web/tiers/archive.py`,
  `src/a2web/handlers/{wikipedia,reddit,twitter}.py`: the direct
  `trafilatura.extract` calls, deleted in favour of the shelf extractor.
- `src/a2web/tiers/__init__.py`: `Rendered` gains `links`.
- `tests/architecture/`: the trafilatura funnel guard.
- `tests/capabilities/link_discovery/` (or nearest existing home): the new guard.
- **Behaviour change for callers**: pages served by browser/jina/zyte/firecrawl/
  archive begin returning `other_pages` where they previously returned none, and
  their `content_md` begins carrying inline links. Both are the documented
  contract being met for the first time on those paths, not a new feature — but
  they change bytes on the wire and token counts, so `make bench` is required.
- **MEASURED, and it does not ship:** `include_links=True` changes only how
  `content_md` renders — the structured `links` come back either way — and it
  flattened a 3-item bulleted listing to 0 bullets. The flag was the most
  obvious-looking half of the fix and was the wrong half. See design D2.
- **No shelf change required.** `content_extract` already exposes everything
  needed. This change is about a2web CONSUMING it, which is why "promote more to
  the shelf" is the wrong lever here — see design D1.
