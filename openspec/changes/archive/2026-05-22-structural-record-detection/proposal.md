## Why

`generic-record-extraction` (v0.14) shipped record extraction, but a 10-page corpus spike found two structural holes the original 4-fixture validation missed.

1. **The recall trigger is blind to structure loss.** The escalation gate (`trafilatura_under_extracted`) is a text-*volume* ratio. trafilatura can keep ~all of a page's text while destroying ~all of its structure: the lobste.rs homepage flattens 25 stories into a wall — volume recall **0.99**, so the trigger never fires, and record extraction never runs. The trigger fails on exactly the text-heavy listing markup it most needs to catch.
2. **The detector can't see threaded regions.** C1 ("≥5 content-bearing repeats as *direct children of one container*") assumes flat siblings. A comment thread is a recursive tree — `li.comments_subtree` nests inside itself, scattered across N containers, none with ≥5 direct children — so `extract_records` returns `None` and the thread is gutted.

The spike validated a fix across articles, catalogs, threads, reference docs, and composite pages: a tree-aware document-wide detector with self-gating guards, replacing the trigger entirely.

## What Changes

- **Remove the recall trigger.** Delete `trafilatura_under_extracted`, `_visible_text_length`, the ratio constants — and the already-dead `count_sentences` / `_SENTENCE_END_RE` (~70 lines from `domain.py`). The detector becomes **self-gating**: it runs unconditionally and "`extract_records` returned a `RecordSet`" *is* the "this page is a listing" classification. No trigger, no separate page-type classifier.
- **Tree-aware detection.** Replace the "direct children of one container" C1 with: locate the dominant repeated signature **document-wide**, root it at the lowest common ancestor, and render each occurrence at its nesting **depth**. This unifies flat catalogs (depth 0) and nested threads (depth > 0).
- **Four self-gating guards** (spike-validated on the corpus):
  - **non-empty class token** on the record signature — kills the reference-doc false positive (Python docs render as repeated heading-bearing `<section>`s with empty class).
  - **parent-signature consistency ≥ 0.70** — kills scattered page chrome (e.g. GitHub nav mega-menus).
  - **heading-presence ≥ 0.50** — kills article prose paragraphs.
  - **ancestor tie-break** — on a score tie, pick the outer wrapper that carries the full record / threading.
- **Depth-aware replace decision.** A thread render (depth > 0) replaces `content_md` whenever the detector produced one — trafilatura cannot produce threading at all, and a length check would *reject* it (proven: trafilatura flattens the lobste.rs thread to 8080 chars; the structured threaded render is a more compact 5062). A catalog render (depth 0) replaces on length, as today.
- **Dual-link `next_links`.** A forum / aggregator record has two destinations — the *discussed page* and the *discussion*. Emit up to two `next_links` per record: `kind="source"` (the heading link) and `kind="discussion"` (a same-host permalink, identified generically by a comment-count anchor like `"N comments"`). Today only one is emitted. Dedup by href; skip archive-mirror hosts. `next_links` is still emitted for catalogs only (depth 0) — a thread's records are not drilldown targets.
- **`record_extract.py` → `record_extract/` package folder** (`detector`, `render`, `models`) — it outgrows a single file.
- No envelope change — `FetchResponse` / `AskResponse` shape is unchanged; `content_md` and `next_links` carry better values.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `extraction`: the recall-trigger requirement is **removed** — the escalation ladder runs unconditionally and each rung self-gates; the quality-aware replace becomes depth-aware (a thread render wins regardless of length).
- `record-extraction`: detection becomes tree-aware (document-wide signature, LCA-rooted, depth-aware render) instead of flat-children C1; adds the four guards; records carry per-record `depth`; `next_links` becomes dual-link (source + discussion) and catalog-only.

## Impact

- **No new dependencies** — tree-aware detection builds on `lxml`, already present.
- Code: `domain.py` (delete the trigger + dead `count_sentences`), `fetcher.py` (`_run_extraction_escalation` runs the ladder unconditionally; `_escalate_via_records` depth-aware replace; `_records_to_next_links` dual-link), `packages/record_extract.py` → `packages/record_extract/`.
- Validated on a 10-page corpus: articles and reference docs correctly return `None`; GitHub trending, lobste.rs home, lobste.rs comment threads, and Douban groups detect correctly.
- Known limitations (documented, out of scope): heading-less `<table>` listings with no site handler stay missed (HN-style — but HN has a handler); composite pages whose comments are client-rendered (Habr) — comments are absent from raw HTML, a separate access concern; near-empty pages (StackOverflow raw) are browser-tier territory.
- Benchmark: re-run `make bench` — lobste.rs and Douban listing extraction expected to improve; `next_links` populated on un-handled listing pages.
