## Why

Today every `ask(url, Q)` call sends the full page content through Haiku at fresh-input pricing, even when the same agent asks five questions on the same URL within seconds. The Anthropic / OpenAI prompt cache exists precisely for this access pattern (10× cheaper on cache reads), but a2web's current prompt assembly does not satisfy the prefix-stability and explicit-marker requirements that make caching fire.

Two specific defects:

1. **`WEBFETCH_DEFAULT_V1` interpolates `{ask}` in the middle of the user template**, with the rules boilerplate (~400 chars, static across calls) sitting *after* the variable. The "cacheable prefix" tail is therefore polluted by per-call variation. Even OpenAI's automatic prefix cache cannot help.
2. **`AnthropicProvider` sends the user message as a flat string** with no `cache_control` blocks. Anthropic's Messages API does not auto-cache — explicit `cache_control: {type: "ephemeral"}` markers are required.

The token-accounting infrastructure is already in place — `AnthropicProvider` destructures `cache_creation_input_tokens` / `cache_read_input_tokens` from `response.usage` and applies the correct 1.25× / 0.10× pricing tiers. The wiring exists; the markers don't.

Probe confirmed (2026-05-23): `claude-agent-sdk` has **zero** `cache_control` references in its installed source. The SDK shells out to the `claude` CLI subprocess and sends `{"role":"user","content": <flat string>}` — there is no API surface to insert breakpoints. The CLI binary applies caching internally and relies on the caller keeping a byte-stable prefix. So **Claude Code SDK needs no marker code from us**; it only needs the template reshape.

## What Changes

- **prompts.py**: add a new template `EXTRACT_CACHEABLE_V1` whose shape is cache-friendly: rules in `system`, page content as a stable user-message prefix, `{ask}` strictly at the tail. `WEBFETCH_DEFAULT_V1` SHALL remain byte-frozen (it is the WebFetch-parity eval anchor) — we do not reshape it. The new template is opt-in via `Extractor(template=EXTRACT_CACHEABLE_V1)`.
- **extractor.py**: introduce a structured `PromptParts` boundary type (`system: str`, `cache_prefix: str`, `tail: str`) returned by a new `PromptTemplate.render(content, ask)` method. The two-string seam keeps providers free to place cache breakpoints between `cache_prefix` and `tail`. Non-cacheable templates collapse into a one-block render.
- **providers/anthropic.py**: switch user content to `[{"type":"text","text":<cache_prefix>,"cache_control":{"type":"ephemeral"}}, {"type":"text","text":<tail>}]`. Add `cache_control` to the system block when non-empty. Keep the existing fallback path for templates that don't opt in to caching.
- **providers/claude_code.py**: NO marker changes. Per probe: SDK has no `cache_control` API. The CLI handles caching internally given byte-stable prefix discipline. We only need to ensure the prompt we hand to `query()` keeps `{ask}` at the tail — which the new template already guarantees.
- **providers/base.py**: widen the `Provider.complete()` signature so callers can pass `cache_prefix` + `tail` separately. Providers that don't care can concatenate. Default behavior unchanged for any provider that doesn't override.
- **Default template wiring**: `build_llm_extractor` selects `EXTRACT_CACHEABLE_V1` for production `ask`. `WebFetchBaseline` (eval anchor) continues to use `WEBFETCH_DEFAULT_V1` unchanged.
- **Tests**: a prefix byte-stability snapshot test that renders the new template with three different `{ask}` values and asserts the `system + cache_prefix` bytes are identical across all three. This guards against future PRs accidentally reintroducing variable bytes into the cacheable prefix.

Not changing: any wire surface (`AskResponse`, `FetchResponse`, tool signatures), the `WEBFETCH_DEFAULT_V1` eval anchor, `ExtractionCache` (sqlite layer-2 cache stays), `extract_token_counts` (already handles cache_creation/cache_read), or the OpenAI / OpenRouter providers (they need no code change — auto-prefix-cache kicks in once the prefix is stable and ≥1024 tokens).

## Capabilities

### New Capabilities

None — pure refactor of the prompt assembly + provider wire shape. No new agent-visible behavior.

### Modified Capabilities

- `extraction`: the existing requirement "`Extractor` runs `(content, ask)` through an LLM and returns an answer" is unchanged in observable contract. A new internal requirement covers the rendered prompt's prefix-stability discipline.

## Impact

- **Code**: ~80-100 LoC added across `prompts.py`, `extractor.py`, `providers/anthropic.py`, `providers/base.py`. Two LoC of marker addition is most of the Anthropic-side fix; the rest is the new template + `PromptParts` plumbing.
- **Dependencies**: none.
- **Cost**: on a multi-Q session against the same URL within TTL, Q1 pays cache-write (1.25× input price), Q2-N pay cache-read (0.10× input price) on the page-content tokens — which dominate any long-page extraction. Estimated 60-70% reduction in input-token cost on multi-Q sessions. Single-Q sessions see a small *increase* (1.25× on the one write) — net positive only when ≥2 questions hit the same URL within TTL.
- **Wire surface**: unchanged. `AskResponse.tokens.cache_creation` / `cache_read` start showing non-zero values; these are debug-tier fields, already regrouped under `debug` by the wire serializer.
- **Tests**: existing extractor + provider tests pass without change (they assert on output text + usage shape, not message-block structure). New snapshot test guards prefix stability.
- **Eval harness**: `WebFetchBaseline` continues to use the byte-frozen `WEBFETCH_DEFAULT_V1`. The new `EXTRACT_CACHEABLE_V1` may be added as a *separate* eval system later if we want to compare quality + cost head-to-head. Out of scope for this change.
- **`packages/` rule**: not impacted — all changes live within `packages/llm_extract`. No cross-package or domain imports added.
- **Risk**: low. Anthropic's content-block API is stable and well-documented. The fallback path keeps non-cacheable templates working unchanged. The snapshot test catches accidental prefix-drift in future edits.
