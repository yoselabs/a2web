## Context

The 2026-05-22 `generic-record-extraction` proposal's D6 explicitly rejected extruct as a *replacement* for `json_in_script` — correctly. That framing was about substitution. This change re-opens the question with a different framing: extruct as an *additive* source for the structured-data ranking pipeline.

Microdata and RDFa are real on the open web but small. Microdata is most alive on long-tail e-commerce (storefronts that didn't migrate to LD-JSON). RDFa is alive in academic publishing and library catalogs. OpenGraph is everywhere (every social card preview depends on it) but mostly redundant with trafilatura's title/description extraction — its lift is on long-tail product/article pages where it carries `og:price:amount`, `og:availability`, or article tags that trafilatura's metadata path misses.

The structural argument for adding it: the LLM extractor's prompt is a `pre_rendered.content_md` synthetic surface, and any structured data we surface there lifts answer quality without spending more LLM tokens on noise. Today microdata-bearing pages give us nothing; trafilatura strips them, and `json_in_script` ignores them. The cost of fixing this is ~90-120 LoC and one direct dependency.

The architectural argument: extruct is sans-IO (takes HTML bytes, returns parsed Python objects). It plugs into the existing `_phase_extract` asyncio.to_thread chokepoint cleanly. It is third-party, so it stays out of the `packages/` independence invariant — no rule strain.

## Goals / Non-Goals

**Goals:**
- Make microdata, RDFa, and OpenGraph available as structured-data sources flowing into the same ranking pipeline as `ld_json` / `next_data`.
- Preserve the `JsonPayload` boundary type as the single dataclass crossing the package boundary. Extruct's parsed shapes do NOT leak into domain code.
- Preserve the package-independence rule. Extruct is third-party.
- Stay within the existing six-phase orchestrator. No new phase.
- Keep the sync extruct call behind the existing `asyncio.to_thread` chokepoint in `fetcher._phase_extract`.

**Non-Goals:**
- No microformats v1/v2 (`hCard`, `hRecipe`, etc.). Extruct supports them but their open-web traffic is near-zero in 2026.
- No Dublin Core. Same reason. (Extruct includes it; we just don't add an adapter for it. The payload would be ignored.)
- No first-party RDFa graph processing. We treat RDFa as flat property triples flattened to a key-value table; we do NOT use rdflib's reasoning / OWL features.
- No CSS-selector-based "rough microdata" walker as an alternative — the design decision below explains.

## Decisions

### D1 — Reject extruct; use selectolax for microdata + OpenGraph; drop RDFa

**Decision**: No new dependency. Walk microdata and OpenGraph directly off the selectolax tree (~150 LoC across extractor + adapters). Drop RDFa entirely from this change's scope.

**Why** (inverted 2026-05-23 mid-implementation, after extruct was briefly added):

Initial framing favored extruct because the RDFa cross-over made any hand-rolled approach heavier. That framing assumed RDFa coverage was worth paying for. It is not — on the a2web eval corpus today, RDFa hit rate is zero, and the only segment that ships RDFa heavily (academic publishing) is already covered by the `arxiv` handler. RDFa is the entire reason extruct pulls `rdflib` + `pyrdfa3` + `mf2py` + `w3lib` + `pyparsing` + `webencodings` transitively (~MB-scale).

With RDFa out of scope, the math flips back:

- *Microdata walker on selectolax* (~50 LoC): we already load the DOM there for the script-tag detectors. The HTML5 microdata spec is a tractable attribute walk: scope discovery, property collection, per-tag value resolution (meta→content, a/link→href, img→src, time→datetime, etc.).
- *OpenGraph collector on selectolax* (~10 LoC): `<meta property="og:*|article:*|product:*|book:*|profile:*">` and pull `content=`.

Total: ~60 LoC of extractor + ~80 LoC of adapters in `domain.py`. Zero new dependencies. No transitive surface change. The "library" pitch was illusory — `python-microdata` is dead since 2017, and there is no maintained microdata-only library; extruct is the only living option and it always pulls rdflib.

**Alternatives reconsidered**:
- *Stay on extruct*: rejected mid-implementation — the rdflib weight is only justified if RDFa lifts the corpus, and we have no signal it does. Reversible: add extruct back if a real RDFa-shaped failure surfaces in a future eval run.
- *Hand-rolled microdata only, no OG*: rejected — OG is the cheapest lift on the same code path (10 LoC) and covers the long-tail product/article gap that trafilatura misses.
- *Different lib for microdata only*: rejected — no maintained option exists.

**Trade-off acknowledged**: we now own the microdata value-resolution table and itemscope nesting walk. Both are stable HTML5 spec surface (microdata hasn't changed since ~2013) so the maintenance cost is near zero. The schema.org type list (`Product`, `Article`, etc.) is already maintained in `_PREFERRED_LD_TYPES` for the LD-JSON path and reused for microdata strong-vs-weak gating.

### D2 — `JsonPayload` stays the only boundary type; new `JsonSource` literals widen the discriminator

**Decision**: Add `"microdata" | "rdfa" | "opengraph"` to the `JsonSource` Literal. Each extruct result becomes one `JsonPayload(source=..., data=..., script_id=None, byte_size=<json-dump-byte-count>)`.

**Why**: One boundary type means one adapter seam (`domain.py::json_to_markdown_rows`). The dispatcher there grows by three cases. Downstream code (`fetcher._phase_extract`, the LLM-prompt builder) doesn't need to know that microdata exists — it just receives ranked `JsonPayload`s.

**Alternatives considered**:
- *New `StructuredPayload` type for the three new sources*: rejected — duplicates `JsonPayload`'s shape and forces every consumer to handle two types.
- *Keep extruct's native shapes through to the formatter*: rejected — leaks extruct's import into domain code and bypasses the `packages/` boundary discipline.

### D3 — Ranking bucket order

**Decision**: `rank_payloads` bucket order:

```
0  ld_json (strong: Product/Article/ItemList/BreadcrumbList/NewsArticle, ≥3 fields)
1  microdata (strong: same @type set, ≥3 fields)
2  next_data, nuxt_data
3  opengraph (always after framework state — it's metadata, not body)
4  ld_json (weak), microdata (weak)
5  window_var
6  generic
7  rdfa (last — flat triples, low signal-to-noise without a markdown adapter)
```

**Why**: Microdata is structurally identical to LD-JSON when the page actually ships it well, so it deserves bucket 1. OpenGraph is metadata-only — it never beats parsed body content. RDFa lands at the bottom because the flattened-triple representation is verbose and most pages with RDFa also ship better structured data via other sources.

**Alternatives considered**:
- *Microdata above LD-JSON*: rejected — when a page ships both, LD-JSON is canonically the better source (deduped, well-typed). Microdata is the consolation prize.
- *OpenGraph in bucket 0*: rejected — it's metadata, not content.

### D4 — Async chokepoint via the existing `_phase_extract` to_thread wrap

**Decision**: The `extract_json_payloads(html)` function in `packages/json_in_script.py` stays sync. The orchestrator's `_phase_extract` continues to wrap the call via `asyncio.to_thread`. The extruct invocation lives inside `extract_json_payloads`, so it's covered by that wrap automatically.

**Why**: One chokepoint per sync subsystem is the project rule (ASYNC100/210/230 lint enforces). Adding a new chokepoint inside the package boundary would violate that rule. The existing wrap is sufficient.

**Alternatives considered**:
- *Per-syntax to_thread wraps inside the package*: rejected — adds ceremony, fragments the chokepoint.

### D5 — `disable_rdfa` setting is deferred until measurement says we need it

**Decision**: Do not ship a `disable_rdfa` AppSettings field in this change. If `make bench` shows p50 fetch-time regression > 5%, add the setting as a fast-follow.

**Why**: Premature config. Measure first.

**Alternatives considered**:
- *Ship `enable_extruct: bool = True` as a kill switch*: rejected — adds one more conditional in `_phase_extract` with no demonstrated need.

### D6 — Adapter strategy for the three new shapes in `domain.py`

**Decision**:

- **Microdata** → reuse `_ld_json_to_markdown` (microdata's `@type` / `properties` map onto LD-JSON's `@type` / direct-keys after a trivial flattening pass).
- **OpenGraph** → small flat-table adapter (`og:title`, `og:type`, `og:url`, `og:image`, `og:description`, `og:price:amount`, plus any `article:*` / `product:*` namespaces). Render as a two-column markdown table.
- **RDFa** → render as a triples table (`subject | predicate | object`). Truncate at ~30 rows.

**Why**: Microdata reuse minimizes net new code. OG and RDFa get explicit adapters because their shape isn't `@type`-like.

**Alternatives considered**:
- *Treat OG as part of trafilatura's metadata path, not the JSON pipeline*: tempting, but it would split the structured-data plumbing across two seams. Keep it in one place.

## Risks / Trade-offs

- **[rdflib parse cost on pages without any RDFa]** → *Mitigation*: extruct's RDFa path short-circuits on no `property=` / `typeof=` attributes. Measured cost is low when no RDFa attributes present. If `make bench` shows regression, ship D5's `disable_rdfa` setting.
- **[extruct's transitive dep weight (rdflib, mf2py)]** → *Mitigation*: known cost. Locked at `extruct>=0.18,<1`. Future swap to lighter library is possible if one appears; the adapter seam in `domain.py` is the only thing that would change.
- **[microdata `Product` shape divergence from LD-JSON]** → *Mitigation*: write the microdata→LD-JSON-shape flattener with explicit field-by-field mapping. Add fixture tests for at least two real Shopify-class pages.
- **[OpenGraph noise on pages where it's just default `og:site_name` cruft]** → *Mitigation*: OG bucket sits after framework state (bucket 3), so when there's a Next.js app-state present, OG is ranked behind it. On bare HTML pages where OG is all we have, it's still better than nothing.
- **[RDFa's flat-triples render is verbose]** → *Mitigation*: truncate at 30 rows. Anything past that is unlikely to be in the LLM extractor's context budget anyway.
- **[Two structured-data outputs for one page may confuse the LLM extractor]** → *Mitigation*: `rank_payloads` already serializes to a ranked list; the prompt builder takes the top-1 (or top-2 with a separator). Existing logic.
- **[Code-vs-spec drift on `window_var`]** → *Opportunity*: this change documents the `window_var` source in the spec (it exists in code but the json-extract spec doesn't mention it). Bring the spec back in line with code as part of this change.

## Migration Plan

1. Add `extruct>=0.18,<1` to `pyproject.toml`. `uv lock`. Confirm rdflib + mf2py land in the lockfile.
2. Widen `JsonSource` Literal in `packages/json_in_script.py`. Add the documentation for `window_var` (close existing drift) and the three new sources.
3. In `extract_json_payloads`, append three extruct passes (one per syntax) and wrap their results in `JsonPayload`. Keep extruct call inside the existing function so the to_thread wrap in `_phase_extract` covers it.
4. Extend `rank_payloads` with the new buckets per D3.
5. Add microdata / OG / RDFa adapters in `domain.py` per D6.
6. Add fixtures + scenario tests for each new source.
7. Run `make bench` against the existing eval corpus + 1-3 new microdata-bearing entries. Confirm answer quality lifts and p50 fetch time stays within 5%.
8. If p50 regresses, ship `disable_rdfa` setting (per D5).
9. Bump version, `make install-global`.

**Rollback**: revert. The change is additive; removing it restores the v0.15 structured-data surface unchanged.

## Open Questions

- Should microdata `Offer` / `aggregateRating` nesting flatten into the parent `Product` markdown, or render as a sub-table? *Decide during fixture work* — Shopify pages will tell us which is more legible to the LLM.
- Should we include `microformat` syntax (the v2 microformats `h-entry` / `h-card`)? *Defer* — no demand signal, almost-zero open-web traffic.
- Should the eval corpus gain a permanent "microdata only" category to prevent regressions? *Yes, but track as a follow-up* — corpus expansion is orthogonal to this change's scope.
