## Context

`PromptTemplate.render()` (`prompts.py`) produces a `PromptParts(system, cache_prefix, tail)` triple. Per the v0.19 cache design, providers place `cache_control` markers between `system + cache_prefix` and `tail` (Anthropic direct), or rely on byte-stable concatenation for providers without a marker API. `system` and `cache_prefix` are therefore the cacheable prefix; `tail` is the always-resent variable suffix.

`EXTRACT_ROUTER_V1` currently puts its entire schema-documentation-plus-examples block (~5,800 of `tail`'s 5,816 chars) inside `tail_template`, alongside the one line that's genuinely per-call (`"\nQuestion: {ask}\n"`). This was true from the template's original v0.21 authoring and untouched by the v0.22 (`ask-extraction-token-tuning`) in-place edit, which only added instruction sentences to `system`. Nothing about the schema block depends on `ask` or `content` — it's a constant, yet it's paying full price every call because of where it's placed, not because it needs to be.

## Goals / Non-Goals

**Goals:**
- Move the static schema+examples text into `system` so it becomes part of the cacheable prefix, with zero wording change.
- Preserve the `cache_prefix_template` byte-identity invariant with `EXTRACT_CACHEABLE_V1` — this change never touches `cache_prefix`.
- Keep the eval harness's ability to distinguish pre/post-move runs via the existing version-bump convention.

**Non-Goals:**
- Not trimming or rewording the schema/examples content itself (a separate, riskier lever — flagged in proposal.md as future work, would need `make bench`).
- Not touching the `{content}` menu-assembly duplication (og:image dims, cross-candidate title/url repetition) — a distinct, larger-blast-radius concern (touches shared rendering code used by every fetched page) outside this change's scope.
- Not changing `EXTRACT_CACHEABLE_V1` (the non-routing template) at all.

## Decisions

**D1 — Relocate, don't reword.** The move is purely mechanical: cut the schema/examples block out of `tail_template`, paste it into the `system` tuple as an additional string joined by `system`'s existing `\n\n` separator. This keeps the change auditable as "same bytes, different bucket" rather than conflating a caching fix with a content-quality change — the two are genuinely separable levers (see proposal.md's "Not in scope" framing) and bundling them would make it harder to attribute any output-quality shift to the right cause.

**D2 — Bump `version` 2 → 3, keep `name` stable.** Matches the exact precedent this template's own comments already document for the v0.22 edit: "bumped to version=2 in place (same name=..., so template_name cache/log keying stays stable while eval history can still tell pre/post-tuning runs apart)". This move changes the rendered `system`/`tail` boundary (observable in logs/eval traces even though the aggregate text is unchanged), so the same reasoning for distinguishing runs applies.

**D3 — No `make bench` run required.** `make bench`'s stated purpose (`CLAUDE.md`) is to catch changes that could move *answer quality* or *cost* in ways worth quantifying — extraction pipeline shape, tier routing, `next_links` behavior. This change moves zero content and changes zero instructions the model reads; the *aggregate* prompt the model sees is byte-identical in total content, merely reorganized across `system`/`tail`. The only externally observable effect is a caching behavior change (invisible to answer quality) and a `template_name`/version bump (observability only). A live single-call sanity check (same question, same URL used throughout this session) is enough to confirm the model's behavior is unaffected; a full live-network eval run would spend real LLM quota measuring something this change doesn't touch.
  - *Alternative considered*: run `make bench` anyway for extra safety. Rejected as disproportionate — reserved for changes with a plausible quality/cost delta, and there isn't one here beyond the caching mechanism itself.

## Risks / Trade-offs

- **[Risk] Some provider path might not actually apply a `cache_control` breakpoint to `system` the way the v0.19 design assumes (e.g. a provider adapter that only caches `cache_prefix`, not `system`).** → Mitigation: this is pre-existing, orthogonal risk — every other instruction already in `system` (the WebFetch-parity rules, the terseness/partial-signal instructions from v0.22) is subject to the identical caching assumption today. This change doesn't introduce a new dependency on that assumption, it just adds more content to a bucket already relied upon for caching.
- **[Trade-off] `system` grows substantially (from ~1,683 to ~7,500 chars).** → Accepted: this is exactly the point — the content was always going to cost tokens somewhere; moving it to the cacheable bucket is strictly better than leaving it in the uncacheable one, never worse.
- **[Risk] A test asserts on the literal `tail_template`/`system` boundary rather than end-to-end behavior, and breaks non-obviously.** → Mitigation: `tests/packages/llm_extract/test_prompt_cache_stability.py` is the named home for this invariant — read and update it explicitly as part of implementation (task list), not discovered by surprise via a red `make check`.

## Migration Plan

No data migration. Pure prompt-template internals — ship behind `make check` plus the live single-call sanity check described above. No feature flag. Rollback is a plain revert (no external state depends on the `system`/`tail` split shape).
