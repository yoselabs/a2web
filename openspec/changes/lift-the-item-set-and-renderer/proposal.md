## Why

Two of the three rows in the 2026-07-31 rule-of-three ledger land here, and one
of them is a **live ADR-0015 violation**.

### Row 2 — the item set, and the live hole

"A set of items on a page" is one concept with **seven-plus incompatible
spellings**, and the four operations over it — render · derive next-links ·
cap-and-declare · project to wire — are re-implemented at each site:

`record_mine.RecordSet` (`fetcher.py:1723`), `_records_to_next_links:1788`,
`_records_to_options` (`fetcher_response.py:234`), JSON-LD `ItemList`
(`domain.py:433`), HN front page (`hn.py:125,160`), Discourse
(`discourse.py:196-244`), arXiv (`arxiv.py:262,311`), Reddit
(`reddit.py:562,610`), GitHub/Wikipedia candidates-only.

**The divergence is a product hole, not an aesthetic one.** The DOM record-miner
path derives `next_links` **and** `options`. The JSON-LD path renders the *same
item set* and derives **neither**. A listing page whose items live in `ItemList`
JSON-LD ships markdown with an empty `other_pages`, while the identical page
mined from the DOM ships both. That is an ADR-0015 violation — the withheld-body
index dropped — caused purely by two unrelated copies of one concept.

Caps diverge with no owner: markdown 30/50/25/25, candidates 10/**50**/10/10/5.
`discourse.py:227` emits up to 50 `next_links` against a cap of 10 everywhere
else — and `handler_probe.py:177` records "observed 30" as healthy, **pinning the
outlier green.** `openspec/specs/link-discovery/spec.md:37` states a single
"capped at 10" invariant implemented as four hardcoded literals, so the spec's
own cap cannot be changed in one place.

Cap-and-declare is the *under*-applied half: only `arxiv.py:283` and
`_reddit_html.py:260` declare truncation. `hn.py`, `discourse.py` and
`reddit.py` listings all truncate **silently** — a withheld-body index that is
itself silently truncated.

### Row 1 — a 360-line renderer with zero domain coupling

`domain.py` is 551 lines doing three jobs:

| job | lines | share |
|---|---|---|
| structured-data → markdown renderer (`:188-551`) | 381 | **69.1%** |
| URL policy | 107 | 19% |
| settings-coupled glue (`compute_profile_hash`, `is_live_only`) | **12** | **2.2%** |

CLAUDE.md and the module's own docstring both describe it as *"pure functions
reading `AppSettings` or models but too small to deserve their own module."*
That describes **12 of 551 lines**. The renderer reads neither settings nor
models, has **zero a2web imports**, is `tach.toml`-eligible for `packages/`
today, and **four test files already aim at it as a unit**. The test tree treats
it as a package; only the source file disagrees.

**Three accidental divergences prove nobody maintains it as one thing:**

- `_opengraph_to_markdown:531` hand-rolls its own markdown table rather than
  calling `_rows_to_md_table` twelve lines above — cell cap **200** vs **80**,
  row cap **50** vs **none**, same escaping, same header shape.
- `_single_entity_md:345` is explicitly default-keep, and its docstring argues an
  allowlist *"silently loses an unanticipated answer-bearing field"*.
  `_recipe_md:316`, immediately above it, **is** that allowlist. The stated
  invariant is violated by its neighbour.
- The cap `50` appears as a bare literal at `:285`, `:439`, `:548` — one of them
  commented "matching `_find_product_or_item_list`", a documented manual sync.

Also: `parse_query_params` is in `__all__`, documented at length, has 6 tests,
and has **zero call sites in `src/`**. Conversely `strip_reader_prefix` is *not*
in `__all__` yet is imported by `fetcher.py:56`. `__all__` no longer describes
the module.

## What Changes

- **Fix the live ADR-0015 hole first, on its own.** The JSON-LD `ItemList` path
  derives `next_links` and `options`, as the DOM path does. This is shippable
  before any lift and should not wait for one.
- **Give the item set one type and four operations.** Whatever the spelling at
  the source, the set converges on one representation, and render /
  derive-next-links / cap-and-declare / project-to-wire each have one
  implementation.
- **One cap, owned.** `link-discovery`'s "capped at 10" becomes a single
  declaration the four literals read. `discourse.py:227`'s 50 is corrected — and
  `handler_probe.py:177`'s "observed 30 is healthy" baseline is corrected with
  it, since it currently pins the violation green.
- **Cap-and-declare everywhere.** `hn`, `discourse`, `reddit` listings declare
  truncation the way `arxiv` and `_reddit_html` already do.
- **Lift the renderer out of `domain.py`** into `packages/` — it already
  qualifies. `domain.py` is left as the ~120 lines its docstring describes.
- **Resolve the three divergences during the lift**, not after: one table
  renderer with one cap pair, the `_recipe_md` allowlist reconciled against the
  default-keep invariant it contradicts, and the bare `50`s named.
- **Fix `__all__`** — drop `parse_query_params` or find it a caller; add
  `strip_reader_prefix`, which is imported today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `link-affordances`: the withheld-body index SHALL be derived from an item set
  regardless of which source produced it.
- `link-discovery`: the link cap SHALL have one declaration; a truncated set
  SHALL declare its truncation.
- `json-extract`: structured-data rendering SHALL have one table renderer and one
  field-retention policy.

## Impact

- `src/a2web/domain.py` — 551 lines → ~120; renderer moves to `packages/`
- `src/a2web/packages/` — new package for the structured-data renderer (Ask
  First: promoting to `packages/` is on the list)
- `src/a2web/handlers/{hn,discourse,reddit}.py` — truncation declaration
- `src/a2web/handlers/discourse.py:227` — cap corrected 50 → 10
- `src/a2web/fetcher.py`, `src/a2web/fetcher_response.py` — item-set operations
- `tests/capabilities/.../handler_probe.py:177` — the baseline that pins the
  outlier
- `openspec/specs/link-discovery/spec.md:37` — the cap gains one implementation
- **Wire change:** JSON-LD listing pages start shipping `other_pages` and
  `options` where they shipped none. That is the ADR-0015 fix, and it is a
  correction rather than a regression — but it is an envelope change.

## Out of Scope

- The remaining handler page-rendering shape (the largest un-elevated shape in
  `src/`, per the primitives scan). Related, larger, and it wants the item set to
  exist first.
- Promoting the renderer to the shelf. Get it into `packages/` with a boundary
  first; `repay-the-shelf-debt` covers the shelf side, including the
  `json-in-html` normalization gap this renderer is the evidence for.
- `reddit.py`'s four retrieval channels behind one `matches()`. Same track (T5),
  separate change.

## Ordering

Split the live fix from the lift. **Ship the JSON-LD `next_links`/`options`
derivation as the first commit**, before touching structure — a product hole
should not wait on a refactor, and shipping it first means the lift is a pure
move with a witness already in place.
