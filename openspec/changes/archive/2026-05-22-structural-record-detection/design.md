## Context

`generic-record-extraction` (v0.14) added a record-extraction rung to the extract phase, gated by `trafilatura_under_extracted` — a recall trigger that escalates when `content_md` is small *relative to the visible text* in the raw HTML. The detector itself (`extract_records`, C1) finds "≥5 content-bearing repeats as direct children of one container."

A 10-page corpus spike (articles, catalogs, threads, reference docs, composite pages) found the v0.14 design has two structural holes that the original 4-fixture validation missed:

- The recall trigger is a text-**volume** ratio. trafilatura flattens the lobste.rs homepage's 25 stories into an undifferentiated wall — it keeps 99% of the *text* while destroying 100% of the *structure*. Volume recall ≈ 1.0, the trigger stays silent, record extraction never runs.
- The C1 detector assumes flat siblings. A comment thread is a recursive tree (`li.comments_subtree` nested inside itself, scattered across 13 `ol.comments` at varying depth); no single container has ≥5 direct-child records, so `extract_records` returns `None`.

Three spike iterations (`/tmp/spike_tree_detect*.py`, `spike_v3.py`, `spike_discuz.py`) validated the fix and surfaced — then closed — two false positives.

## Goals / Non-Goals

**Goals:**
- Detect listing **and** threaded-discussion regions generically, with no per-site logic and no page-type classifier.
- Remove the volume trigger — the detector's own correctness becomes the gate.
- Preserve both record destinations: the discussed page and the discussion.
- No envelope / wire change.

**Non-Goals:**
- Heading-less `<table>` listings with no site handler (HN-style) — stay missed; HN has a handler, this is long-tail.
- Composite pages whose comments are client-rendered (Habr) — comments are absent from raw HTML; a browser-access concern, not a detection one.
- Near-empty pages (StackOverflow raw fetch) — browser-tier territory.
- A new article extractor — trafilatura stays the article path.

## Decisions

### D1 — Remove the recall trigger; the detector self-gates
A volume/text proxy is structurally incapable of seeing "text survived, structure destroyed" (lobste.rs home: ratio 0.99). The fix is not a better trigger — any structural trigger would have to do the detector's own work. Instead: run the detector unconditionally, and treat its return value as the classification — a `RecordSet` means "this is a listing," `None` means "it is not." Delete `trafilatura_under_extracted`, `_visible_text_length`, `_UNDER_EXTRACTED_RATIO`, `_NEAR_EMPTY_FLOOR`, and the already-dead `count_sentences` / `_SENTENCE_END_RE` (~70 lines). **Alternative rejected:** a structural trigger (count repeated siblings in raw HTML) — that *is* the detector; running it twice buys nothing. The near-empty → browser path does not need the trigger: the gate (`evaluate`) already has a length floor that drives `suggested_tier`.

### D2 — Tree-aware detection: document-wide signature, LCA-rooted, depth-aware render
Replace C1 ("direct children of one container") with: count each `(tag, first-class-token)` signature **document-wide**; the dominant content-bearing signature's occurrences are the records; root them at their lowest common ancestor; render each at its nesting **depth**. `depth(el)` = count of ancestors sharing the signature. This unifies flat catalogs (`li.story` ×25, depth 0) and recursive threads (`li.comments_subtree` ×11, depth 5) under one algorithm. Render uses **own-scope** text/links — a record's text excludes its nested child-records, so an outer comment is not double-counted. **Alternative rejected:** flattening recursive containers into one sibling list — loses the threading, which is the whole value of a discussion page.

### D3 — Four self-gating guards (each closes a spike-proven false positive/negative)
- **Non-empty class token** on the record signature. Reference docs (Python docs) render as repeated heading-bearing `<section>`s — structurally indistinguishable from a listing *except* the class is empty. Real listing/thread records carry a semantic class (`story`, `comment`, `Box-row`, `athing`). Spike: `section.-` ×17 → rejected, nothing else changed.
- **Parent-signature consistency ≥ 0.70.** Real records sit under one repeating container signature; scattered chrome does not. Spike: GitHub's nav mega-menu `div`s scored consistency 0.33 → dropped, so the real `article.Box-row` (1.00) wins despite a lower raw score.
- **Heading-presence ≥ 0.50** of records contain `h1`–`h6` or `[role=heading]`. Kills article prose paragraphs (`<p>` runs with inline links).
- **Ancestor tie-break.** On a score tie, prefer the signature that is a parent-signature of another tied candidate — the outer wrapper carries the full record / threading (`li.story` over `div.story_liner`; `li.comments_subtree` over `div.comment`).

### D4 — Depth-aware replace, not length-only
A catalog render (depth 0) replaces `content_md` when it is longer than trafilatura's output (proven: gh-trending 7053 > 1524; lobste-home 17345 > 3897). A **thread** render (depth > 0) replaces whenever the detector produced one — *regardless of length*. Proven necessary: trafilatura flattens the lobste.rs comment thread to 8080 chars; the structured threaded render is a more compact **5062** — a `len(synth) > len(traf)` check would reject the strictly-better output. trafilatura cannot produce threading at all, so a passing thread RecordSet is unambiguously better. The guards (D3) are the article protection — every article in the corpus returns `None` before the replace check is even reached.

### D5 — Dual-link `next_links`: source + discussion
A forum / aggregator record has two destinations. Verified on lobste.rs: every `li.story` carries `a.u-url` → the discussed external article, **and** an `"N comments"` anchor → the `/s/…` thread. Emit up to two `NextLink`s per record: `kind="source"` (the heading link) and `kind="discussion"` (a same-host link whose anchor matches a comment-count pattern `\d+\s*comments?`, or whose path is a thread permalink). Dedup by href; skip archive-mirror hosts (Archive.org / Ghostarchive duplicates appear in the link set). `next_links` is emitted for **catalogs only** (depth 0) — a thread's nested records are already inline, nothing to drill into.

### D6 — Catalog vs. discussion is `depth`, not a classifier
There is no page-type classification step. The detector computes one structural fact per record — `depth` — and two downstream rules key on it: render indents by depth; `next_links` is emitted only at depth 0. "Catalog" and "discussion" are descriptions of flat vs. nested record-sets, never an `enum` or an `if page_type`. The principle behind D5's depth-0 gate is structural: a nested record already contains its children inline, so there is nothing to drill into.

### D7 — `record_extract.py` → `record_extract/` package folder
Tree detection + depth render + four guards + boundary types outgrow a single file. Split into `detector.py`, `render.py`, `models.py` — matching `llm_extract/` and `cookie_store/`. Still package-pure: no `a2web.<domain>` imports; `tests/test_packages_independence.py` enforces it.

## Risks / Trade-offs

- **Article-with-card-widget false positive** — a true article carrying a 6-card "related posts" widget → Mitigation: the widget RecordSet is small; D4's length check rejects it against the longer article. The guards already reject most; the replace check is the backstop.
- **Heading-less listing missed** — a bare `<table>` or image grid with no headings, no handler → Mitigation: accepted. The detector returns `None`, trafilatura output stands — no worse than today. The heading gate's false-negative risk is the price of killing the reference-doc false positive.
- **Tree-aware detection cost on every fetch** — always-run, per-element own-scope computation → Mitigation: spike timing was 17–270 ms across the corpus, noise next to trafilatura (70–2800 ms). The real implementation computes own-scope text without per-element `deepcopy`.
- **Detector picks a secondary region on a composite page** — an article page with a comment section → Mitigation: D4 length check keeps a substantial article; a comment thread that genuinely dominates the page is the correct pick anyway.

## Migration Plan

Phased, each phase `make check`-green:
1. **Phase 1 — tree-aware detector + guards.** New `packages/record_extract/` (detector, render, models); document-wide signature, LCA, depth render, the four guards.
2. **Phase 2 — remove the trigger.** Delete `trafilatura_under_extracted` & friends from `domain.py`; `_run_extraction_escalation` runs the ladder unconditionally; each rung self-gates.
3. **Phase 3 — depth-aware replace + dual-link `next_links`.** `_escalate_via_records` branches on `depth`; `_records_to_next_links` emits source + discussion.
4. **Verify** — re-run `make bench`; lobste.rs / Douban listing extraction should improve, no article regression.

No envelope change → no client migration. Rollback: revert restores the v0.14 trigger + flat detector.

## Open Questions

- The `0.70` / `0.50` guard thresholds are corpus-tuned (10 pages) — widen the benchmark corpus and retune if a real miss appears.
- Whether the shared "tree → threaded markdown" renderer should be extracted to `packages/` now (the Discourse / Habr handlers will want it) or after the first handler lands — deferred to the handler proposals.
