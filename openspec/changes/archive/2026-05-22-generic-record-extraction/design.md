## Context

The generic extract phase is `raw HTML → trafilatura → content_md`. trafilatura is an article extractor: it locates one main-content node and discards the rest as boilerplate. On listing / index pages there is no single "article" — the page *is* N repeated records — so trafilatura keeps the item descriptions and drops the repeated link grid as navigation.

a2web already has a thin-trafilatura escalation slot — `_maybe_synthesize_from_json` in `fetcher.py` — but it has exactly one recovery strategy (`json_in_script`, embedded `<script>` JSON) and one trigger (`content_md < 2048 chars OR < 3 sentences`). Server-rendered listing pages carry no embedded JSON, so the slot fires, finds nothing, and gives up. The benchmark's `gh-trending` cell scored 0/5 for `a2web_extract` for exactly this reason.

A spike (`/tmp/a2web_spike/`) established two facts: (1) trafilatura config flags (`favor_recall`, `include_links`, `include_tables`) recover **1 of ~25** repo slugs on GitHub trending — a dead end; (2) a ~120-line structural detector located the dominant record region correctly on 4/4 content-bearing pages (GitHub trending, danluu, lobsters, simonwillison), with page chrome correctly ranked below.

## Goals / Non-Goals

**Goals:**
- "Thin" means *trafilatura under-extracted*, not *output is short* — a recall signal, not a length threshold.
- Generalize the escalation slot into a multi-source ladder.
- A generic structural record extractor: locate the dominant record region, render it to link-preserving markdown, emit `next_links`.
- `gh-trending` moves from 0 to passing; `next_links` populated on un-handled listing pages.
- No envelope / wire change.

**Non-Goals:**
- XHR-interception for pure-JS SPAs (browser captures the API response) — deferred; needs a failing corpus case first.
- microdata / RDFa extraction (extruct) — JSON-LD is already covered by `json_in_script`; the rest is a thin slice, deferred.
- A new article extractor — trafilatura stays the article path.
- Per-site listing handlers — the generic extractor is the *floor*; existing API-backed handlers remain the high-quality path.

## Decisions

### D1 — Recall-based trigger, not a length threshold
Escalate when `content_md` is small *relative to the substantive content present in the raw HTML*, not when it is small in absolute terms. A complete 1500-char article has high recall (trafilatura kept ~everything) → not thin. A gutted listing has low recall → thin. **Alternative rejected:** tightening the `2048` constant — still a length proxy, still false-positives on short articles, and once the record extractor exists a false-positive trigger risks clobbering a good article.

### D2 — The escalation slot generalizes; sources do not collapse into a config dial
`json_in_script` (parse `<script>` JSON) and structural record detection (repeated-DOM mining) are different *algorithms*, not settings of one extractor. The ladder is: JSON-in-script → record extraction → fall through to browser tier. **Alternative rejected:** a single "extraction level" knob — the operations are not points on one dial.

### D3 — Split record extraction into C1 (locate) and C2 (render)
C1 locates the dominant repeated content-bearing region. C2 renders that *bounded* subtree to markdown, preserving every link. The split matters: the research (NEXT-EVAL) measured classic MDR at F1 ≈ 0.083 — but that brittleness is in *field alignment*, not region location. The spike confirmed region location is robust (4/4). C2 never guesses a "primary field" (the spike showed the first link in a record is often chrome — a Star/Sponsor button, a `/login` link); it renders the whole bounded record keeping all links, and lets the downstream LLM / synth pick.

### D4 — Pragmatic structural detection, not full tag-path clustering
The spike's detector — "the container whose direct children include the most repeats of one signature, each child carrying real text + ≥1 link" — sufficed on every test page. Ship that; do not port the full Miao et al. tag-path occurrence-vector clustering unless the benchmark shows misses. **Alternative rejected:** MDR / DEPTA — abandoned OSS, brittle on modern markup.

### D5 — Quality-aware replace, not "≥2× chars"
The escalation result replaces `content_md` only when it is a dominant *substantive* record cluster (N records, each with text + a link, N above a floor). The current `len(synth) ≥ 2 × original` rule would, once record detection runs, swap a good 1500-char article for a 4000-char related-posts / tag-cloud widget. Length is not quality.

### D6 — JSON-LD via the existing `json_in_script`, not extruct
`json_in_script` already detects `<script type="application/ld+json">` (`source="ld_json"`) and `rank_payloads` already prefers `ItemList`. The only gap is the synth adapter `json_to_markdown_rows` not understanding the `ItemList` / `itemListElement` shape. Extend that. **Alternative rejected:** the `extruct` library — it would re-buy JSON-LD parsing a2web already owns, add a dependency, and contribute only microdata / RDFa.

### D7 — `record_extract` lives under `packages/`
Pure HTML → records, no `a2web.<domain>` imports. Boundary types (`Record`, `RecordSet`) are package-owned; the domain seam converts them to `content_md` + `NextLink`. `tests/test_packages_independence.py` enforces it.

### D8 — Multi-listing pages: render the single top-ranked region in v1
The spike found simonwillison's homepage carries two genuine listings (posts + link-blog). v1 renders the top-ranked region only. Top-N rendering or question-driven disambiguation is deferred until the benchmark shows a miss.

### D9 — The ladder runs uniformly across tiers
The escalation runs in `_phase_extract` after `extract_markdown`, so it covers raw, browser, and archive results uniformly — consistent with v0.11 having already extended JSON synth to browser-rendered DOM.

## Risks / Trade-offs

- **Chrome ranked as records** (nav / footer / sidebar repeats) → Mitigation: the content filter (per-record text length + ≥1 link), ranking by `records × median_text`, and the quality-aware replace guard (D5). The spike confirmed GitHub's `MarketingNavigation` list ranked below the real records.
- **Article-with-comments false positive** — a short article whose page has a large comment cluster → Mitigation: replace only when the detected cluster is dominant *and* trafilatura's output is not already substantive; the recall trigger plus D5 keep a good article in place.
- **Detection brittle on exotic markup** — the spike was 4/4 but small → Mitigation: "no dominant region" is a clean, defined outcome — the ladder falls through to the browser tier rather than emitting garbage (the spike's `pypi-search` cell, which fetched a near-empty body, exercised exactly this and produced zero false records).
- **`next_links` first-link-is-chrome** → Mitigation: C2 preserves *all* links in the record; `next_links` selection uses the record's heading / most-prominent link, not link index 0.

## Migration Plan

Phased, each phase `make check`-green:
1. **Phase 1 — recall trigger.** Replace the length gate. Prerequisite: it must land before the record extractor, or the extractor clobbers short articles.
2. **Phase 2 — record extractor + ladder.** New `packages/record_extract/`, the C1/C2 split, the multi-source ladder in `_phase_extract`, quality-aware replace.
3. **Phase 3 — JSON-LD `ItemList` synth + `GitHubHandler` reserved-path skip-set.**
4. **Verify** — re-run `make bench`; `gh-trending` should move 0 → passing.

No envelope change → no client migration. Rollback: the ladder is additive over the existing JSON-only escalation; reverting restores prior behavior.

## Open Questions

- Exact recall-ratio threshold for D1 — tune against `eval/corpus.yaml` during Phase 1.
- Whether the v1 top-1 region render (D8) misses real multi-listing pages — revisit if the benchmark shows it.
