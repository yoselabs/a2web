## Why

The generic extraction path assumes every page is an article. trafilatura locates one main-content node and discards everything else as boilerplate — so listing / index pages (GitHub trending, search results, blog indexes, link aggregators) come out gutted: the item descriptions survive, but the repeated link structure that *is* the page gets dropped as "navigation." The output benchmark proves the cost: `gh-trending` scored **0/5** for `a2web_extract` against WebFetch's **5/5**, because the extractor received slug-stripped fragments. Listing pages are a whole page archetype with zero generic coverage — today they only work if a per-site handler exists.

A throwaway spike confirmed the fix is viable: a ~120-line structural detector located the dominant record region correctly on GitHub trending, danluu, lobsters, and simonwillison — and confirmed trafilatura config flags (`favor_recall`, `include_links`) recover nothing.

## What Changes

- **Recall-based "thin" trigger.** Replace the absolute-length escalation gate (`content_md < 2048 chars`) with a recall signal — escalate when trafilatura *under-extracted* relative to the substantive content present, not merely when output is short. A complete short article stops triggering escalation; a gutted listing starts. This is a prerequisite: without it, the new record extractor would clobber good short articles.
- **Multi-source escalation ladder.** Generalize the single-strategy thin-trafilatura escalation (`_maybe_synthesize_from_json`, JSON-in-script only) into an ordered ladder of structured-extraction sources, falling through to the browser tier when nothing applies.
- **New structural record extractor.** Locate the dominant repeated record region in server-rendered HTML (spike-validated) and render that bounded subtree to markdown with links preserved. Populate `next_links` from the detected records — un-handled listing pages produce zero `next_links` today.
- **JSON-LD `ItemList` synthesis.** `json_in_script` already detects `ld_json` payloads and `rank_payloads` already prefers `ItemList`; extend the synth adapter (`json_to_markdown_rows`) to render an `ItemList` into records. No new dependency.
- **Quality-aware replace decision.** The escalation result replaces `content_md` only when it is a dominant *substantive* record cluster — not merely longer. The current `≥2× chars` rule would clobber a good short article with a related-posts widget once record detection is in play.
- Fix the `GitHubHandler` false-match on reserved top-level paths (`/trending`, `/sponsors`, …).
- No envelope change — `FetchResponse` / `AskResponse` shape is unchanged; `content_md` and `next_links` simply carry better values on listing pages.

## Capabilities

### New Capabilities
- `record-extraction`: structural detection and extraction of repeated data records from listing / index HTML — locate the dominant record region, render it to link-preserving markdown, emit records as `next_links` candidates. Pure HTML → records, lives under `packages/`, no domain imports.

### Modified Capabilities
- `extraction`: the thin-trafilatura escalation is redefined — recall-based trigger instead of absolute length; a multi-source ladder (JSON-in-script → record extraction → browser) instead of JSON-only; quality-aware replace instead of `≥2× chars`; the synth adapter handles the `ItemList` shape.

## Impact

- **No new dependencies.** Record detection builds on `lxml` / `beautifulsoup4` (already present); JSON-LD is already parsed by `json_in_script`. (extruct was considered and dropped — a2web already extracts JSON-LD; extruct would only add microdata / RDFa, a thin slice, deferred.)
- Code: `fetcher.py` (`_phase_extract`, `_maybe_synthesize_from_json` → escalation ladder), new `packages/record_extract/` (pure, package-independent), `domain.py` (`json_to_markdown_rows` `ItemList` shape), `handlers/github.py` (reserved-path skip-set).
- The escalation ladder must run uniformly for the raw, browser, and archive tiers (JSON synth was already extended to browser-rendered DOM in v0.11).
- Benchmark: `gh-trending` expected to move 0 → passing; `next_links` populated on un-handled listing pages where it is empty today. Re-run `make bench` after.
- Out of scope: XHR-interception for pure-JS SPAs (browser tier captures the API response rather than re-extracting the rendered DOM) — deferred; needs a failing corpus case before it earns a build.
