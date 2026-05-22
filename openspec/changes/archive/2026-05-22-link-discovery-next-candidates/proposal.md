## Why

Multi-step research workflows (Reddit listing → individual posts, AliExpress / HEPCB listing → product detail, HN front page → comments, GPU review aggregator → review pages) currently leave the agent guessing which links matter. The `links` array dumps every href flat, the agent has to scan and guess from anchor text alone, and on listing-style pages 60–80% of those hrefs are nav/UI noise. The result: agents either drill blindly (burning tokens fetching the wrong pages) or skip the drilldown entirely (missing the actual answer — prices live on detail pages, not listings). We need a curated, ranked set of "links worth following next" returned alongside the answer so the agent can act on intent, not anchor-text heuristics.

## What Changes

- Add a new `next_links: list[NextLink]` field on `FetchResponse`. Each entry carries `anchor`, `url`, `reason` (one phrase: why this matters for the current question), and `kind` (`drilldown` / `related` / `source`). Capped at 10 entries.
- **Tier 1 — Handler-known structure:** site handlers (Reddit, HN, arXiv, GitHub, Wikipedia) populate `next_links` deterministically from their structured output (e.g. Reddit listing → permalinks with titles + scores; HN → story URL + comments URL per row). Zero LLM cost.
- **Tier 2 — LLM-curated from markdown:** when `ask=` is set and no handler-known structure applies, extend the existing `ask=` extraction prompt to return `{answer, next_links}` in the same call. The LLM picks from inline links already present in `content_md`. One LLM call total, no second pass.
- **Tier 1 + Tier 2 composition:** when both apply (handler produces candidates AND `ask=` is set), the LLM re-ranks the handler's candidate set against the question rather than unioning two lists ("top posts" vs "find posts about RTX 5090" want different orderings of the same permalinks).
- New tool param `next_links: bool = True` on `fetch` to suppress the field when the agent knows it won't drill down (saves a few hundred tokens on terminal fetches).
- Link aliasing / short-ID addressing is **explicitly out of scope** — stays on BACKLOG until we measure that full-URL pass-through is the actual bottleneck.
- Server-side recursive drilldown (`follow_depth=N`) is **explicitly out of scope** — passive candidates first; active recursion only after we see whether agents pick the right candidates.

## Capabilities

### New Capabilities
- `link-discovery`: Curated set of "what to fetch next" candidates returned alongside the answer. Owns the `NextLink` model, the response-envelope contract, the Tier 2 LLM-curation prompt extension, and the Tier 1+2 composition rule. Handler-specific candidate population is owned by `site-handlers` (modified capability below) — `link-discovery` only specifies the contract handlers feed into.

### Modified Capabilities
- `site-handlers`: each existing handler (Reddit, HN, arXiv, GitHub, Wikipedia) gains a requirement to populate `next_links` from its structured tier-0 output when the URL is a listing-style page (Reddit subreddit listing, HN front page, arXiv listing). Permalink-style URLs (single Reddit thread, single arXiv paper) typically have no drilldown layer and SHALL return an empty candidate list.
- `extraction`: the LLM `ask=` extraction prompt and return contract gain an optional `next_links` output field. The existing `answer` field stays — `next_links` is additive.

## Impact

- **Code:**
  - `src/a2web/models.py` — new `NextLink` pydantic model at module scope; `FetchResponse` gains the optional list field.
  - `src/a2web/fetcher.py` — orchestrator threads `next_links` from handler result + LLM extract output into the final response. New `_phase_compose_candidates` (or inline in existing `_phase_extract`) handles Tier 1+2 composition.
  - `src/a2web/handlers/*.py` — five handlers (`reddit`, `hn`, `arxiv`, `github`, `wikipedia`) populate candidates on listing URLs.
  - `src/a2web/packages/llm_extract/prompts.py` (or equivalent) — `ask=` prompt extended to request `next_links`; provider response shape extended.
  - `src/a2web/routers.py` — `fetch` tool gains `next_links: bool = True` param.
- **API / wire shape:** additive on `FetchResponse`. Existing clients ignoring unknown fields are unaffected. MCP schema regenerates.
- **Dependencies:** none new.
- **Tests:** new fixtures for Reddit-listing-with-candidates, HN-front-page-with-candidates, arbitrary-page-with-ask-and-candidates. The `test_packages_independence` invariant stays green (no domain imports into `packages/`).
- **Cost / latency:** Tier 1 is free. Tier 2 adds a few hundred tokens of output to the existing `ask=` call (single call, no extra round-trip). Default-on is acceptable because the win on drilldown flows dominates; `next_links=False` is the escape hatch.
- **Docs:** README "fetch tool" section gets a `next_links` subsection; one example showing the Reddit-listing drilldown flow.
- **Backlog cleanup:** the v0.4+ "discovery / next-link curation" + "alias-addressed links" entries in `BACKLOG.md` get rewritten — discovery moves into this change, aliases stay deferred with an explicit "prerequisite shipped in this change" note.
