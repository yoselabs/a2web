## Context

Rows 1 and 2 of the rule-of-three promotion ledger
(`docs/findings/2026-07-31-primitives-scan.md`). Row 1 is described there as the
highest promotion ratio in the repo; Row 2 carries a live ADR-0015 violation.

Both are the same failure at different scales: a concept that exists in the
codebase N times, where the *drift between the copies* is the proof nobody
maintains them as one thing.

## Goals / Non-Goals

**Goals**

- A listing page ships the same index whether its items came from the DOM or from
  JSON-LD.
- One cap declaration, honoured everywhere, with truncation declared.
- `domain.py` matches its own docstring.
- The renderer's three internal divergences are resolved, not carried across.

**Non-Goals**

- Promoting to the shelf. `packages/` first, with a boundary.
- Handler page-rendering generally — the larger shape, which wants the item set
  to exist first.
- Any change to what the renderer produces for a page it already handles, beyond
  the three divergences.

## Decisions

### D1 — Ship the ADR-0015 fix before the lift

The JSON-LD `ItemList` path deriving neither `next_links` nor `options` is a live
product hole. It could be fixed today in isolation.

Do that, as the first commit, before any structural work. Two reasons: a product
hole should not wait on a refactor, and shipping the fix first means the lift has
a witness in place — the corpus case proving both paths agree exists *before* the
code moves, which is exactly the foreign-provenance discipline the repo already
requires.

The inverse order — lift, then fix — makes the fix's test a fixture written
against the new structure by the same person who wrote the structure.

### D2 — The item set is one type with four operations

The four operations are already identifiable at every site: render,
derive-next-links, cap-and-declare, project-to-wire. What varies is the input
spelling and the caps.

So the type is the convergence point, not a base class: each source produces the
one representation, and the four operations are written once against it.
`record_mine.RecordSet` is the closest existing shape and the natural starting
point.

The reason to state this rather than "unify the item set": there are two ways to
unify N copies, and the polymorphic one (a protocol each site implements) leaves
four operations × N sites. The convergent one leaves four operations, full stop.

### D3 — One cap, and the probe baseline moves with it

`openspec/specs/link-discovery/spec.md:37` states a single "capped at 10"
invariant. It is implemented as four hardcoded literals (`arxiv.py:317`,
`hn.py:169`, `reddit.py:612`, and only `wikipedia._WIKILINK_CAP` named), plus
`discourse.py:227` at 50.

Declare it once. But note the trap: `handler_probe.py:177` records "observed 30"
as healthy for discourse. Correcting the cap without correcting the baseline
turns the probe red for the right reason and it will read as a regression;
correcting the baseline without the cap pins the violation green, which is what
it does today.

Move them together, and say in the commit that the baseline was recording a
defect as health.

### D4 — Cap-and-declare is the half that matters for ADR-0015

`arxiv.py:283` and `_reddit_html.py:260` declare truncation. `hn.py`,
`discourse.py`, `reddit.py` do not.

A silently truncated index is worse than a small one: the caller is told what is
elsewhere, believes the list is the list, and never re-fetches for the rest.
That is the ADR-0015 harm arriving through the index instead of through the body.

`arxiv.py:297`'s `Papers (25 of 408)` + partial-view note is the pattern; it is
also the only cap in the codebase that reports its own truncation, and its
docstring cites the bench measurement that forced it. Port it.

### D5 — The renderer goes to `packages/`, and the divergences are resolved in the move

It qualifies today: zero a2web imports, `tach.toml`-eligible, four test files
already treating it as a unit.

The three divergences must be resolved **during** the move, not filed as
follow-ups:

- **Two table renderers.** `_opengraph_to_markdown:531` hand-rolls one twelve
  lines below `_rows_to_md_table` — cell cap 200 vs 80, row cap 50 vs none, same
  escaping, same header shape. Pick one cap pair deliberately; do not preserve
  both by keeping both renderers.
- **The allowlist that contradicts its neighbour.** `_single_entity_md:345` is
  explicitly default-keep and argues in its docstring that an allowlist *"silently
  loses an unanticipated answer-bearing field"*. `_recipe_md:316` is that
  allowlist. One of the two is wrong and the module cannot say which. Decide,
  and record the decision — this is an ADR-0015-adjacent question (what is
  silently dropped), not a style question.
- **Three bare `50`s** (`:285`, `:439`, `:548`), one commented as a manual sync.
  Name it.

Carrying a documented manual sync across a package boundary makes it a
cross-package manual sync, which is strictly worse.

### D6 — What stays in `domain.py`

The 12 lines of settings-coupled glue (`compute_profile_hash`, `is_live_only`)
plus the 107 lines of URL policy. ~120 lines, and the docstring becomes true.

**Anti-seam: `is_search_shaped` cannot follow the renderer.** `:36-37` states it
exists to gate `actions.empty.is_confirmed_empty` (`empty.py:70`) — it is one
clause of the ADR-level empty→ok conjunction, not a URL utility.

**Second anti-seam: `_CAPTCHA_SEARCH_HOSTS` (`:77-84`) is coupled to
`packages/block_detector.py:186-190, 305-307` by comment only** — two halves of
one Google/Bing policy, in two modules, linked in prose, with nothing testing the
pair. Do not separate them further. A test over the pair is cheap and is the
right moment to add it.

## Risks / Trade-offs

- **The ADR-0015 fix is a wire change.** JSON-LD listing pages start shipping
  `other_pages` and `options` where they shipped none. It is a correction, but it
  changes the envelope for real callers — say so in the CHANGELOG rather than
  filing it as a bug fix.
- **Correcting discourse's cap 50 → 10 loses 40 links** on pages that were
  shipping them. That is the spec's stated invariant, but it is a reduction in
  what a caller receives; the truncation declaration is what makes it honest.
- **Promoting to `packages/` is on the Ask First list.** Boundary types need
  design and the seam may need conversion logic — that is exactly why the
  divergences are resolved in the move rather than after.
- **`_recipe_md` vs `_single_entity_md` is a genuine product decision.** Whoever
  resolves it is deciding what a recipe page silently drops. Do not resolve it
  by picking the shorter diff.

## Open Questions

- Which cap pair survives — 200/50 or 80/none? The 80 came first and the 200 has
  no stated derivation, but neither is measured. Pick and record; do not average.
- Is `_recipe_md`'s allowlist right for recipes specifically, or is it the
  general default-keep rule wrongly narrowed? If the former it stays as a
  documented exception with its reason; if the latter it goes.
- `parse_query_params`: dead in `src/` with 6 tests and an `__all__` entry.
  Delete it, or is there a caller intended? Deleting a documented public function
  is the honest default when nothing calls it.
- Does the item set type live in `packages/` with the renderer, or does it
  straddle (the wire projection half is domain-coupled)? The renderer is pure;
  `project-to-wire` may not be able to follow it.
