## Why

Live-rendered `EXTRACT_ROUTER_V1` this session (`EXTRACT_ROUTER_V1.render(content=..., ask=...)`) and measured the three `PromptParts` buckets: `system` = 1,683 chars (cached, per the v0.19 cache design), `cache_prefix` = the page content (cached), `tail` = 5,816 chars (**not cached** — resent in full on every single `ask` call). Of that 5,816-char `tail`, only `"\nQuestion: {ask}\n"` (~20 chars) actually varies per call. The remaining ~5,800 chars — the `structural_form`/`shape` enum definitions, the `obstacle`/`ask_here`/`try_url`/`item_total_seen`/`refinement_axes` field documentation, and all 4 worked JSON examples — are 100% static: identical across every page, every question, forever. They live in `tail_template`, the one bucket the v0.19 cache design deliberately does NOT mark cacheable, because `tail` is supposed to be the genuinely-variable part of the prompt.

This means a ~1,450-token block is paid in full on every `ask` call regardless of how many calls happen in quick succession within the same session — the exact shape of a typical multi-fetch research or product-comparison session. Moving that static content into `system` (which is already cached) costs nothing on the first call and saves the full block on every repeat call within the provider's cache window (Anthropic's default TTL is 5 minutes).

## What Changes

- `EXTRACT_ROUTER_V1.tail_template` narrows to just the per-call question (`"\nQuestion: {ask}\n"`). The schema documentation and all 4 worked examples move into `EXTRACT_ROUTER_V1.system`, appended after the existing routing-helper framing sentence. No wording changes to the instructions themselves — a pure relocation between buckets.
- `cache_prefix_template` is untouched — still `"Web page content:\n{content}\n"`, byte-identical to `EXTRACT_CACHEABLE_V1`'s, preserving the v0.19 cache-prefix invariant this template's own comments call load-bearing.
- Bump `PromptTemplate.version` from `2` to `3` in place (same `name="extract_router_v1"`), matching this template's own established convention for a rendered-shape change (the v0.22 comment already documents doing exactly this for a smaller in-place edit) — keeps `template_name` cache/log keying stable while letting eval history distinguish pre/post-move runs.
- Update the `extraction` capability's "Extractor supports an opt-in request_routing mode" requirement, which currently mandates the schema live in `tail` — it now mandates the schema live in `system` (still never in `cache_prefix`).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `extraction`: the "Extractor supports an opt-in request_routing mode" requirement's mandate that the router-shape schema append to `parts.tail` changes to `parts.system` — the cache-prefix invariant (schema/content never touches `cache_prefix`) is unchanged, only which cacheable-vs-uncacheable bucket the static schema text lives in.

## Impact

- `src/a2web/packages/llm_extract/prompts.py` — `EXTRACT_ROUTER_V1` template body + its version-history comment block.
- `openspec/specs/extraction/spec.md` — delta spec for the affected requirement.
- Tests referencing `EXTRACT_ROUTER_V1`'s rendered `system`/`tail` boundary (to be located and updated during implementation) — `tests/packages/llm_extract/test_prompt_cache_stability.py` in particular, since it's named for exactly this invariant.
- No wire/envelope change, no tool signature change. Pure prompt-template internals — verified via a live re-render (byte-level bucket check) and one live `ask` call for output-quality sanity, not a full `make bench` run (no wording change, so no expected quality delta — see design.md for the reasoning on why bench isn't warranted here).
