## 1. Template edit

- [x] 1.1 In `src/a2web/packages/llm_extract/prompts.py`, move `EXTRACT_ROUTER_V1`'s schema documentation + all 4 worked examples out of `tail_template` and into the `system` tuple, appended after the existing routing-helper framing sentence. Leave `tail_template` as only `"\nQuestion: {ask}\n"`.
- [x] 1.2 Confirm `cache_prefix_template` is untouched (still `"Web page content:\n{content}\n"`, byte-identical to `EXTRACT_CACHEABLE_V1`'s).
- [x] 1.3 Bump `EXTRACT_ROUTER_V1.version` from `2` to `3` (same `name="extract_router_v1"`).
- [x] 1.4 Update the template's version-history comment block documenting this move and why (mirrors the existing v0.22 comment's style).

## 2. Tests

- [x] 2.1 Read `tests/packages/llm_extract/test_prompt_cache_stability.py` and any other test referencing `EXTRACT_ROUTER_V1`'s rendered structure; update assertions that check the literal `system`/`tail` boundary content to match the new split. Assertions checking `cache_prefix` byte-stability must continue to pass unmodified.
- [x] 2.2 Add/update a test asserting the schema+examples text is now in `system` and stays byte-identical across two different `ask` values for the same `content` (mirrors the new spec scenario).
- [x] 2.3 Run the full test suite; confirm green.

## 3. Verification

- [x] 3.1 Run `make check` (lint + ty + test, coverage ≥85%).
- [x] 3.2 Live re-render `EXTRACT_ROUTER_V1.render(content=..., ask=...)` (same approach used to discover this issue) and confirm: `cache_prefix` byte-identical to before; `system` now contains the full schema+examples; `tail` contains only the question line; total content across all three buckets is unchanged (nothing lost, nothing duplicated).
- [ ] 3.3 One live `uv run a2web web ask` call against the Koçtaş product URL used throughout this session — confirm the answer/quality is unaffected by the prompt reshuffle (same price/stock answer, same `content_guidance` hint behavior).
- [x] 3.4 Do NOT run `make bench` — no content/wording change, no expected quality delta (see design.md D3).
