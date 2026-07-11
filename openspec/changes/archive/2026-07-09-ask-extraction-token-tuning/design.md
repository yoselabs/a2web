## Context

Two live `ask` calls (Google Translate camera-UI articles) surfaced two independent, purposeful-tuning opportunities:

1. **Wire-side waste.** `AskResponse.meta` (`models.py:671`) is populated from `fc.meta_dict` / `fr.meta` (`fetcher_response.py:376,523`), itself the raw output of the shelf's `content_extract.parse_metadata` — every `og:*` / `twitter:*` / `jsonld[0].*` key, unallowlisted, unconditional (not gated by `include_content` or `debug`, unlike `content_md`/`headings`). `genre` (`models.py:707`) is a real field with a documented v0.21 router-shape rationale but the audit found no downstream reader — it is not consulted by `content_guidance.kind_guidance()`, the incompleteness gate, or the refinement logic (unlike `structural_form`, `shape`, `obstacle`, which are consulted).
2. **Prompt-side under-extraction.** The `ask` tool renders `EXTRACT_ROUTER_V1` (`prompts.py:155`). Its `system` tuple carries quoting/legal rules and the router-classification instruction, but no token-efficiency guidance and no partial-signal honesty rule. `TERSE_V1` (a sibling, non-router template) *does* say "if the content does not contain the answer, say so explicitly" — but that instruction is binary (answer / no-answer), not partial-signal-aware, and `TERSE_V1` isn't even the template `ask` uses. The result observed live: a page listing "Camera" as one of four nav tabs (real, partial signal) produced "the article does not address camera redesign... no specifics" (a denial, not a partial report).

Prior art already exists for exactly the WebFetch-comparison angle raised in discussion: `WEBFETCH_DEFAULT_V1` (`prompts.py`) is a byte-for-byth copy of Claude Code's own WebFetch prompt, with a research note at `~/Documents/Knowledge/Researches/123-claude-code-webfetch-internals/`, and the eval harness (`llm_eval/`, `make bench`) already A/B-tests templates by reflection — "adding one doesn't require a runner change." Backend swappability (the "Claude Code SDK as one option, any-LLM as another" question) is also already solved: `provider-selection` supports `claude-code` / `anthropic` / `openai_compatible` (any OpenAI-compatible endpoint) with a documented preference order. No new work needed there — this design just confirms and documents it.

## Goals / Non-Goals

**Goals:**
- Curate `AskResponse.meta` to a small, high-value allowlist; leave `FetchResponse.meta` (via `fetch_raw`) untouched as the full raw dump for debug/inspection use — `parse_metadata` itself is not modified, only how `AskResponse` projects it.
- Remove `genre` from the `AskResponse` wire (dead weight — zero consumers).
- Add a token-efficiency instruction to `EXTRACT_ROUTER_V1.system`: terse framing, zero fact/identifier/number loss, ASCII-preferring punctuation where meaning is unaffected.
- Add a partial-signal honesty instruction to the same `system` block: report what IS present when full detail is missing, rather than denying the topic outright.
- Preserve the byte-stable `cache_prefix_template` invariant (v0.19) — both new instructions land in `system`, never in `cache_prefix_template` or `tail_template`'s content-bearing parts.
- Re-run `make bench` after the prompt change to catch quality regressions on the four existing axes (answer quality, token cost, clarity, contract conformance) before considering this done.

**Non-Goals:**
- Bumping the default extraction model tier (Haiku → Sonnet) for `ask`. Real quality/cost tradeoff, touches LLM judgment allocation — flagged in the prior audit as needing its own "Ask First" conversation, deliberately deferred out of this change.
- Any change to `structural_form`, `shape`, `obstacle` — each has a confirmed consumer and stays as-is.
- Any change to `parse_metadata` itself, `fetch_raw`'s `FetchResponse.meta`, or the shelf `content_extract` package — the curation happens only at the `AskResponse` projection layer.
- New provider backends or changes to `provider-selection` — already covers the raised "Claude Code SDK vs any LLM" question.

## Decisions

**D1 — Allowlist at the `AskResponse` projection, not at `parse_metadata`.** `parse_metadata` is shared shelf substrate consumed by both `ask` and `fetch_raw`; `fetch_raw` callers legitimately want the full raw dump for debugging/inspection (per its documented role as the no-LLM fallback). Curating only where `AskResponse` is built (`build_ask_response` / the `AskResponse(...)` constructor call site) keeps the shelf package and `fetch_raw` untouched. Alternative considered: curate inside `parse_metadata` itself — rejected, it would silently degrade `fetch_raw`'s value and couples a domain-specific (ask-only) policy into shared substrate.

**D2 — Allowlist keys: `og.description`, `og.site_name`, plus whichever of `jsonld[0].datePublished` / `jsonld[0].author` isn't already covered by the promoted `title`/`byline`/`published` fields.** `og.title` is deliberately excluded — it is a straight duplicate of the already-promoted top-level `title` field (same source, same string), so keeping it would reintroduce exactly the duplication this change exists to remove. `og.description` and `og.site_name` survive because no top-level field carries that signal. Every `og.image*`, `twitter.*`, `og.title`, and `og.locale`/`og.type`/`og.url` key observed in the audit carried zero incremental signal for an `ask` caller. Exact final list is an implementation-time judgment call against a couple of real fixtures — tasks.md will call out "verify against 2-3 live fixtures" rather than pre-committing to an exact set here.

**D3 — Drop `genre` outright rather than debug-gate it.** Unlike `content_md`/`headings` (opt-in via `include_content`) or the debug tier (`started_at`/`cache`/etc., opt-in via `debug=True`), `genre` has no consumer anywhere — not even a diagnostic one. Debug-gating a field nobody reads adds ceremony with no payoff. If genre classification turns out to matter later, re-adding it under `debug=True` is cheap and reversible.

**D4 — New instructions land in `EXTRACT_ROUTER_V1.system`, as an in-place text addition, not a new `EXTRACT_ROUTER_V2` template.** The module docstring frames templates as "frozen, versioned" and the eval harness picks up new templates by reflection — suggesting the intended pattern for a *shape*-changing edit (new required/optional fields, e.g. the v0.21 router-shape rollout itself) is a new versioned constant. This change is not shape-changing — no new JSON field, no schema change to `RouterPayload` — it's a pure instruction-tuning edit to existing prose in `system`. `cache_prefix_template` (the actual cache-critical byte-stable string) is untouched. Precedent: `system` isn't part of the v0.19 cache-prefix invariant, only `cache_prefix_template` is. Risk noted below if this reading of the versioning convention turns out wrong.

**D5 — Token-efficiency instruction wording is descriptive-not-prescriptive on ASCII.** "Prefer ASCII punctuation over Unicode look-alikes (curly quotes, em dashes, smart ellipses) where meaning is unaffected" — not an absolute ban, since some source content legitimately requires non-ASCII (quoted foreign text, technical symbols, currency). The instruction targets the model's own prose framing, not verbatim quoted material (which the existing 125-char quote rule already governs character-for-character).

**D6 (addendum, post-shipping exploration) — drop `og.site_name` from the allowlist too, leaving only `og.description`.** A live sweep of 6 real `raw`-tier pages (BBC, TechCrunch, Smashing Magazine, Apple's iPhone page, Project Gutenberg, OpenAI's GPT-4 page) found `og.site_name` present and non-empty in every case, and in every case it was exactly the obvious human-readable form of the domain already visible in the requested URL (`techcrunch.com` → "TechCrunch", `smashingmagazine.com` → "Smashing Magazine"). Zero incremental signal observed. `og.description` remained the only allowlisted key that carried genuinely new content (a page summary distinct from any promoted field) across all 6 samples. Revises D2's original allowlist (`og.description` + `og.site_name`) down to `og.description` alone.

**D7 (addendum) — the shelf's `_flatten_jsonld` already can't reach nested facts, so the allowlist-vs-denylist question doesn't apply to phone/email/address anyway.** Traced the shelf `content_extract._flatten_jsonld`: "Only top-level scalar fields end up in `out`. Nested objects/arrays are skipped." A phone number under `Organization.contactPoint.telephone` never reaches `parse_metadata`'s output regardless of a2web's allowlist/denylist choice — the nesting is dropped one layer earlier, in adopted shelf substrate `ask-extraction-token-tuning` does not touch. This closes the "are we gatekeeping something critical" worry for `meta` specifically: `meta` was never the carrier for such facts. (Separately, `domain.py`'s entity renderer for the *extraction escalation ladder* — a different pipeline entirely — already surfaces single-object `contactPoint`/`address` into the LLM's prompt; see the follow-up change `structured-entity-array-rendering` for the one real gap found there: array-of-object fields, e.g. multiple `ContactPoint` entries, are silently dropped by `_single_entity_md`.)

## Risks / Trade-offs

- **[Risk] The allowlist in D2 turns out too aggressive** — some caller eventually needs an `og.*`/`jsonld` key that got dropped. **Mitigation:** the key is not destroyed, only omitted from `ask`'s lean envelope; `fetch_raw` on the same URL always has the full raw `meta`. Document this fallback path in the `ask-response` spec delta.
- **[Risk] In-place edit to `EXTRACT_ROUTER_V1` (D4) breaks an assumption that templates are immutable once shipped** (e.g. eval history comparing "extract_router_v1" runs across time silently mixes pre/post-tuning behavior under one name/version). **Mitigation:** bump `PromptTemplate.version` from `1` to `2` on the same `name="extract_router_v1"` constant (small, cheap, keeps the "new constant per shape change" convention reserved for schema changes while still giving the eval harness/logs a way to distinguish pre/post-tuning runs). Confirm this reading is acceptable during task execution; fall back to a full `EXTRACT_ROUTER_V2` constant if the version-bump-in-place pattern isn't actually supported by the eval harness's reflection discovery.
- **[Risk] Partial-signal instruction increases verbosity** (models now describing "what IS present" instead of a short denial) — could raise average answer token count, partially offsetting the terseness goal. **Mitigation:** `make bench`'s token-cost axis catches this directly; if it regresses meaningfully, tighten the wording to cap partial-signal reporting at 1-2 sentences.
- **[Trade-off] No model-tier change.** The under-extraction root cause the audit identified is partly a Haiku-capability ceiling, not purely a prompt gap — prompt tuning alone may not fully close the gap. Explicitly accepted as this change's scope boundary; tracked as a deferred follow-up requiring its own discussion.

## Example: Before / After

Real repro (androidheadlines.com camera-redesign article), default call (no `include_content`):

Before:
```json
{
  "confidence": "low",
  "answer": "The article does not address camera screen redesign details, button arrangements, gallery/import photo placement, or iOS rollout information. ...",
  "title": "About Time: Google Translate to Finally Get a Modern App Visual Redesign",
  "byline": "Jean Leon",
  "published": "2026-07-07",
  "operator_hints": [{"code": "retrieval_incomplete", "severity": "critical"}],
  "meta": {"og.locale": "en_US", "og.type": "article", "og.title": "...", "og.description": "...", "og.url": "...", "og.site_name": "Android Headlines", "og.image": "...", "og.image:width": "1920", "og.image:height": "1080", "og.image:type": "image/jpeg", "twitter.card": "summary_large_image", "twitter.creator": "@jeanleon_g", "twitter.site": "@androidheadline", "twitter.label1": "Written by", "twitter.data1": "Jean Leon", "twitter.label2": "Est. reading time", "twitter.data2": "3 minutes", "jsonld[0].@context": "https://schema.org"},
  "retrieval_incomplete": true,
  "headings": [[1, "About Time..."], [2, "A cleaner, roomier layout"]],
  "structural_form": "article",
  "shape": "prose",
  "genre": "news",
  "obstacle": "empty"
}
```

After:
```json
{
  "confidence": "medium",
  "answer": "The article doesn't detail button-level camera-screen changes. It confirms Camera remains one of four sections in the new pill-shaped bottom nav (Translate, Live, Camera, Practice), replacing the old full-width tabs. No mention of a gallery/import-photo button, shutter controls, or iOS-specific rollout dates.",
  "title": "About Time: Google Translate to Finally Get a Modern App Visual Redesign",
  "byline": "Jean Leon",
  "published": "2026-07-07",
  "meta": {"og.description": "Google Translate is getting a modern UI redesign: app code reveals a sleek pill-shaped navigation bar, rounded cards, and better shortcuts.", "og.site_name": "Android Headlines"},
  "structural_form": "article",
  "shape": "prose",
  "ask_here": ["Does the version 10.25 teardown show camera-tab icon changes specifically?"]
}
```

What changed and why: `genre` is gone (no consumer). `meta` drops from 18 raw keys to 2 curated ones (`og.image*`/`twitter.*`/`jsonld[0].@context` carried zero incremental signal beyond the already-promoted `title`/`byline`/`published`; `og.title` itself is dropped too — it's a straight duplicate of the top-level `title` field, same source and string, so keeping it would just reintroduce the duplication this change removes). `headings` is gone because `include_content` wasn't requested (unchanged behavior — it was never meant to appear here). `retrieval_incomplete` and its `critical` operator hint disappear because they were a symptom of the extractor's mis-diagnosis (treating "detail not found" as "topic not found" at all), not an actual retrieval failure — the page fetched fine. `answer` now states the partial signal instead of denying the topic, and `confidence` reflects "partially covered," not a manufactured full miss.

The `include_content=True` variant of the same call is unaffected in shape (`content_md` + `headings` still appear only when requested) — the only change there is the tool-description nudge steering a calling agent toward a separate cache-hit `fetch_raw` call instead of reflexively combining both in one `ask` call.

## Migration Plan

1. Land the `models.py` meta-allowlist + `genre` removal (pure wire trim, no prompt risk) — can ship independently and be verified via the existing `ask-response` capability tests plus new scenarios.
2. Land the `prompts.py` `system` instruction additions + version bump.
3. Run `make bench` (live-network, spends quota — per CLAUDE.md guidance, deliberate manual step, not part of `make check`). Compare pre/post on the four axes; write findings to `eval/findings_<date>.md` per existing convention.
4. If bench shows a clear win or neutral result, this change is done. If it regresses on any axis, iterate on the instruction wording before merging (this is prompt tuning — expect at least one iteration).

## Open Questions

- Exact final `meta` allowlist (D2) — resolved at implementation time against live fixtures, not pre-committed here.
- Whether to bump `PromptTemplate.version` in place vs. a new constant (see risk above) — resolved at implementation time by checking whether the eval harness's reflection discovery keys on `name`, `version`, or both.
