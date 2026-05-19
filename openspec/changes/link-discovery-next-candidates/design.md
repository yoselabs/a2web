## Context

Today the agent flow on a listing-style page is: fetch page → ask question → receive `answer` + flat `links[]`. The agent has no per-link relevance signal beyond anchor text, so it either guesses (wrong page → wasted fetch) or skips the drilldown layer (incomplete answer — prices on detail pages never reach the user). Real-world traces from the 2026-05-11 vs-WebFetch benchmark show this pattern on PyPI, gh-trending, and npm: the listing has the right *set* of next URLs, but no curation; the agent reads `links[]` (which is 49% of payload by tokens) and still picks badly.

We already have two structural advantages a competitor product doesn't:
1. **Site handlers** (Reddit, HN, arXiv, GitHub, Wikipedia) produce *typed* tier-0 output and know exactly which links matter for which URL shapes.
2. **`ask=` LLM extraction** already reads the full page content (including inline markdown links) on every question-answering fetch.

Both can produce curated candidate links cheaply. Tier 1 (handler) is free. Tier 2 (LLM) is free-ish — same call, slightly longer output. Neither needs a new model, a new external service, or a new round-trip.

## Goals / Non-Goals

**Goals:**
- Return a curated, capped (≤10), ranked `next_links` list on every `fetch` response when the page or the question warrants drilldown.
- Zero LLM cost on handler-known pages (Reddit listing, HN front page, arXiv listing).
- Single LLM call on arbitrary pages with `ask=` (no second pass).
- Stable, additive response shape — old MCP clients ignoring the field stay green.
- One ranking when both tiers apply: the question wins, the handler supplies the set.

**Non-Goals:**
- **Link aliasing / short-ID addressing.** Stays on BACKLOG. Only worth it once we measure full-URL pass-through as the actual bottleneck.
- **Server-side recursive drilldown** (`follow_depth=N`). Passive candidates first; we need to see whether agents pick well before adding recursion budgets.
- **Cross-fetch session state.** Each fetch is still stateless; candidates are computed from the current page only.
- **Replacing `links[]`.** `next_links` is additive. Operators who want the raw inventory keep using `include_links=True`.
- **Permalink-style pages drilldown.** A single Reddit thread / single arXiv paper / single HN item has no obvious "layer beneath" — these return an empty candidate list rather than fabricating one.

## Decisions

### Decision 1: Three tiers, picked by what we know about the page

The matrix:

| Page shape | `ask=` set? | Source of candidates |
|---|---|---|
| Handler-known listing (Reddit subreddit, HN front page, arXiv listing) | no | Tier 1 only — handler structured output |
| Handler-known listing | yes | Tier 1 set + Tier 2 re-ranks against the question |
| Handler-known permalink (Reddit thread, arXiv paper) | either | Empty list (no drilldown layer) |
| Arbitrary page | no | Empty list (no signal — agent didn't ask a question, so "relevance" is undefined) |
| Arbitrary page | yes | Tier 2 — LLM picks from inline markdown links in the page it just read |

**Rationale.** Tier 1 is the lowest-cost surface and the highest-precision (the handler knows the page schema). Tier 2 generalizes to the long tail at the cost of one extension to an existing prompt. Both are off by default for cases where curation has no signal (no question + no handler knowledge → don't fabricate).

**Alternatives considered.**
- *LLM-only (drop Tier 1).* Cheaper to ship, but burns tokens on Reddit / HN flows where the answer is mechanical. Rejected on cost.
- *Handler-only (drop Tier 2).* Covers ~5 sites. Doesn't help on PyPI / gh-trending / arbitrary GPU review aggregators — exactly the cases the benchmark flagged. Rejected on coverage.
- *Always include candidates, even without `ask=`.* Forces fabrication on arbitrary pages. Rejected — empty list is honest signal.

### Decision 2: `NextLink` shape

```python
class NextLink(BaseModel):
    anchor: str            # visible link text, ≤120 chars
    url: str               # absolute URL, full (no aliasing in v1)
    reason: str            # one phrase, ≤80 chars: why this link matters
    kind: Literal["drilldown", "related", "source"]
```

- `drilldown` — same topic, deeper layer (Reddit listing → individual thread; AliExpress listing → product detail; HN front page → comments).
- `related` — adjacent question (sibling thread; "see also" link).
- `source` — citation / primary doc (Wikipedia citation footnote; arxiv paper cited in a thread).

Cap: **10 entries** per response. Empty list is the normal "no drilldown" outcome.

**Rationale.** Four fields is the minimum that lets an agent decide without re-fetching. `reason` is the load-bearing field — without it the agent is back to anchor-text guessing. `kind` lets a planning agent batch ("drill down on all drilldowns first, surface `source` to the user").

**Alternatives considered.**
- *Free-form string list.* Drops `reason` and `kind`. Rejected — defeats the curation point.
- *Score / probability.* Looks rigorous, but the LLM has no calibrated meaning for "0.7" and the handler has no way to produce one. Ranking is implicit (list order). Rejected.

### Decision 3: Tier 1 — handler populates candidates from existing structured output

Each affected handler already parses a structured response (Reddit JSON, HN Algolia tree, arXiv Atom). Candidate construction is a pure transform on data already in memory — no extra HTTP, no extra parse. The handler returns `TierResult.next_links: list[NextLink]` (new typed field on `TierResult`, alongside `pre_rendered`).

- **Reddit listing** (`/r/<sub>/` or `/r/<sub>/hot/`) — top 10 permalinks with `reason = f"{score} score, {num_comments} comments"`, `kind="drilldown"`. NB: PR5's Reddit handler matches comment URLs only — listing matching is added here.
- **HN front page** (`news.ycombinator.com/`) — top 10 story URLs with comments URL paired (`reason="comments"` on the discussion link); both `kind="drilldown"`. NB: PR5's HN handler matches `item?id=N` only — front-page matching is added here.
- **arXiv listing** (`arxiv.org/list/<cat>/<yymm>`) — top 10 abs URLs with title-as-anchor, `reason="abstract"`, `kind="drilldown"`.
- **GitHub** — repo URL exposes README anchor links + `/issues` + `/pulls` as `kind="related"`. Issue/PR URLs return empty (already terminal).
- **Wikipedia** — top 10 outbound article links (from `wikilinks` in Parsoid output), `kind="related"`. Citation footnotes are `kind="source"`.

**Rationale.** Handlers know schema. Pulling 10 entries from already-parsed JSON is free.

### Decision 4: Tier 2 — extend the `ask=` extraction prompt to emit `next_links`

The current `ask=` provider call returns `{answer: str, ...}`. We extend the system prompt with: *"Also return up to 10 `next_links` — links present in the markdown that would help answer the question better if fetched. Use `drilldown` for the deeper layer of the same topic, `related` for sibling questions, `source` for citations. Empty list if the answer is complete."*

The provider response schema gains an optional `next_links: list[NextLink]` field. All providers already speak JSON output; this is a schema extension, not a new call shape.

**Rationale.** Folding curation into the existing extraction call is the only way to get this for free. The LLM already read the page — re-reading it in a second call is pure waste.

**Trade-off.** Slightly longer output (~200–400 tokens worst case). Acceptable — the listing pages this targets routinely save thousands of tokens on the *next* fetch by picking the right URL.

### Decision 5: Composition — when both tiers fire, the LLM re-ranks the handler's set

If a handler produced `next_links` AND `ask=` is set:
1. Pass the handler's candidate list into the `ask=` prompt as an additional system message: *"The site handler suggests these candidates. Re-rank, filter, and re-explain `reason` against the user's question. You MAY drop candidates that don't match. You MAY add candidates from the markdown if the handler missed an obvious one."*
2. The LLM-returned list replaces (not unions with) the handler's list.

**Rationale.** Question-relative ranking dominates handler-relative ranking. "Top posts" wants score-ordered; "find posts about RTX 5090" wants topic-ordered over the same permalinks. Letting the LLM both re-rank and refine `reason` makes the candidate field actually useful per-query.

**Alternative considered.** *Union both lists.* Doubles the cap; agent gets confused by two `reason` strings per URL. Rejected.

### Decision 6: New `next_links: bool = True` tool param

Default-on because the win on drilldown flows justifies the few hundred tokens on terminal fetches. Off-switch exists for agents that *know* this is the last hop ("I have the price, no drilldown needed").

**Alternative considered.** *Default-off, opt-in.* Forces every drilldown-capable agent to set the flag. Rejected — defaults should favor the high-value path.

### Decision 7: `link-discovery` owns the contract; `site-handlers` owns the population

The `NextLink` model, response-envelope position, tool param, and Tier 2 LLM prompt extension live in the new `link-discovery` capability. Handler-specific candidate population (Reddit listing → permalinks, etc.) is added to `site-handlers` as new requirements per handler.

**Rationale.** The contract is cross-cutting (one tool param, one response field, one prompt extension). Handler population is per-handler — five separate scenarios live more naturally in `site-handlers/spec.md` alongside the existing per-handler requirements.

## Risks / Trade-offs

- **Risk: LLM fabricates URLs not present in the page.** → Mitigation: provider response validation — every `next_links[i].url` MUST appear in either the markdown the LLM was given OR the handler's pre-supplied candidate list. Drop any that don't, log a `Diagnostic` with verdict `extraction_drift`. This is a quality gate, not an exception.
- **Risk: Reason strings turn into marketing fluff** ("comprehensive overview of all your needs"). → Mitigation: prompt requires `reason` ≤80 chars and a fact about *this specific link* (score, date, position). The judge prompt in eval harness gets a "candidates" axis to track this in benchmarks.
- **Risk: Handler-known listing URLs we don't match yet.** Reddit subreddit listing, HN front page, arXiv listing aren't matched by the v0.1 handlers. → Mitigation: this change extends the `matches(url)` patterns for those three handlers. Existing comment / item / abs matchers stay.
- **Risk: Token cost regression on terminal fetches.** Default-on means every `ask=` call gets the extra prompt language and a few hundred tokens of empty `[]` output. → Mitigation: empty-list output is ~10 tokens; the prompt extension is ~100 tokens system-side. Net regression on terminal fetches is bounded. Off-switch covers the rest. Re-measure in the next vs-WebFetch benchmark run.
- **Trade-off: stateless contract preserved.** No alias mapping, no recursion. We trade efficiency-at-scale for simplicity-of-deployment. The BACKLOG entries cover the next moves when we have data to justify them.
- **Risk: handler-supplied candidates leak the wrong privacy / SFW signal.** Reddit listings can mix NSFW. → Mitigation: handler honors `over_18: false` filter when constructing candidates (skip NSFW posts unless URL is an NSFW subreddit listing the user already targeted).

## Migration Plan

1. **No breaking changes.** Additive field on `FetchResponse`; additive param on `fetch`; additive optional field on provider response schema.
2. Ship as v0.7. CHANGELOG entry under "Added".
3. Update README "fetch tool" section with one Reddit-listing drilldown example.
4. Rewrite the two BACKLOG entries that this change subsumes (v0.4+ discovery + v0.4+ aliases) — discovery is removed; aliases stays with a forward reference to this change.
5. Re-run the 2026-05-11 vs-WebFetch benchmark to measure candidate-quality lift on PyPI / gh-trending. Track `next_links_picked_correctly` as a new judge axis.

**Rollback.** Set `next_links: bool = False` default at the tool level — the field becomes opt-in. Handlers keep populating `TierResult.next_links` (cheap), but it never reaches the wire. No code rollback needed if the contract is right.

## Open Questions

1. **Listing-page matchers — does Reddit's `r/<sub>/` actually need its own handler class, or can `RedditHandler` accept both shapes via a branch in `matches()` + `fetch()`?** Lean toward one class with two paths — keeps the registry small. Resolve during specs phase.
2. **GitHub README outbound links — `kind="related"` or `kind="source"`?** Lean `related` (README links are usually peers, not citations). Resolve in handler scenarios.
3. **Should Wikipedia citation footnotes really be `source`, or split them out as a separate `kind="citation"`?** Lean keep as `source` for now; split if benchmarks show ambiguity.
4. **Cap = 10 or 5?** Lean 10. Benchmark on the first Reddit listing run will say whether 5 is enough.
