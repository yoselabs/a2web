## Context

a2web invests Haiku tokens on every `ask`. The page-content portion of the prompt is the dominant token cost — long pages routinely push prompts into the 5K-50K token range. Anthropic's prompt cache (5-minute default TTL, 1-hour extended) drops cache-read tokens to 10% of fresh-input price. OpenAI quietly auto-caches prefixes ≥1024 tokens. Neither provider can help us today because our prompt is structured wrong.

The structural fix is small. The reason it didn't ship earlier is that `WEBFETCH_DEFAULT_V1` was deliberately byte-frozen to match Claude Code's internal WebFetch sub-call (Rb9 template; see research note 123). Frozen-template discipline served the eval comparison well but ruled out any reshape. The right move is a *second* template that breaks parity and is cache-friendly, used in production while the eval anchor stays unchanged.

## Goals / Non-Goals

**Goals:**
- Make the cacheable prefix (`system + cache_prefix`) byte-stable across different `{ask}` values for the same `{content}`.
- Add explicit `cache_control: {type:"ephemeral"}` markers on the Anthropic-direct path. Confirm OpenAI auto-caches once the prefix is stable. Confirm claude-agent-sdk needs no marker code (CLI handles it internally).
- Net cost reduction on multi-Q sessions; no observable wire-surface change.
- A snapshot test that catches future prefix drift.

**Non-Goals:**
- Reshape `WEBFETCH_DEFAULT_V1`. It is the WebFetch-parity eval anchor; do not touch.
- Migrate the eval harness to the new template. That's a separate experiment with its own design.
- Build affordances ("what else this page can answer") into the prompt. Separate change — depends on this one landing first because cheaper extraction reshapes its cost-benefit.
- Extended cache (1-hour) TTL plumbing. Default 5-minute TTL is fine for v1; revisit if probe data shows misses that an hour-cache would have hit.

## Decisions

### D1 — New template `EXTRACT_CACHEABLE_V1`, not reshape the existing one

**Decision**: Add `EXTRACT_CACHEABLE_V1` as a new `PromptTemplate` instance alongside `WEBFETCH_DEFAULT_V1` and `TERSE_V1`. Production `ask` defaults to the new template; `WebFetchBaseline` continues to use the byte-frozen original.

**Why**: `WEBFETCH_DEFAULT_V1` is documented as "byte-for-byte the Rb9 non-preapproved-host template from Claude Code's binary." Its value as an eval anchor is precisely that we can attribute output differences to model / extraction code, not to template drift. Reshaping it would forfeit that comparison forever. Adding a second template costs ~20 LoC and preserves both invariants.

**Alternatives considered**:
- *Reshape `WEBFETCH_DEFAULT_V1` and accept loss of parity*: rejected. The parity anchor is load-bearing for the eval harness; the cost (lose ability to A/B against Claude Code's own WebFetch) outweighs the savings (~10 LoC of template duplication).
- *Make the cacheable shape a parameter on a single template instance*: rejected. `PromptTemplate` is a frozen dataclass — adding a "render mode" flag bleeds policy into a value type. Two named templates is the clearer surface.

### D2 — `PromptParts` boundary type with `system`, `cache_prefix`, `tail`

**Decision**: A new frozen dataclass returned by `PromptTemplate.render(content, ask)`:

```python
@dataclass(frozen=True, slots=True)
class PromptParts:
    system: str          # static across calls (cacheable when non-empty)
    cache_prefix: str    # page content + any static framing — cacheable
    tail: str            # variable per call — NOT cached
```

Non-cacheable templates render with `cache_prefix=""` and the whole user message in `tail`. Providers that don't honor cache markers concatenate `cache_prefix + tail` into a single string — behavior unchanged.

**Why**: The provider needs to know *where* to put the cache breakpoint. A flat string doesn't carry that information. Three named fields are explicit, type-safe, and match the cache topology exactly: system + prefix get markers; tail does not. No `dict[str, Any]` bag. No magic delimiter string in the rendered output.

**Alternatives considered**:
- *Pass a sentinel string in the rendered output that providers split on*: rejected — fragile, leaks policy into prompt bytes.
- *Add `cache_breakpoint_at: int` (character offset)*: rejected — equivalent expressive power but harder to read and harder to assert on in tests.

### D3 — Anthropic-direct gets explicit markers; Claude Code SDK gets stability discipline only

**Decision**:
- `AnthropicProvider.complete()`: when called with `PromptParts`, sends `system` as `[{"type":"text","text":<system>,"cache_control":{"type":"ephemeral"}}]` and user content as `[{"type":"text","text":<cache_prefix>,"cache_control":{"type":"ephemeral"}}, {"type":"text","text":<tail>}]`. Two cache breakpoints used out of the Anthropic API's 4-block budget.
- `ClaudeCodeProvider.complete()`: NO marker changes. Continues to pass `system_prompt=<system>` and `prompt=<cache_prefix + tail>` (concatenated). The Claude CLI binary applies its own caching policy on the assembled API call; our only job is to keep the concatenated prefix byte-stable across different `{ask}` values, which the new template guarantees.

**Why**: Probe of `claude-agent-sdk` (2026-05-23, installed version `0.1.80+`) shows zero `cache_control` references in the SDK source. The SDK shells out to `claude` subprocess via `SubprocessCLITransport` and writes `{"role":"user","content": <flat string>}`. There is no SDK surface to insert content blocks or cache markers. The CLI binary, however, applies caching to its own outgoing API calls (well-established for multi-turn conversation prefixes). Our contract with the CLI is "keep the bytes stable and the CLI will cache appropriately." This is the cheapest possible compliance path for the SDK provider — no code change, just template discipline.

**Confirmation method**: snapshot test asserts `system + (cache_prefix concatenated with each of N different tails)` shares an identical `system + cache_prefix` byte-prefix. This is the actual contract the CLI needs.

### D4 — OpenAI / OpenRouter: no code change required

**Decision**: Do not modify any OpenAI provider code in this change.

**Why**: OpenAI's automatic prefix cache (rolled out 2024-10) fires when the prompt prefix is ≥1024 tokens and byte-stable across calls. No opt-in required, no markers. The template reshape alone gets us the savings. OpenRouter passes through to the chosen backend — auto-caching depends on the backend, and we have no API surface to influence that. The right move is to land this change, then measure OpenRouter cache-hit rates in production telemetry, then decide if a backend-specific marker path is justified.

**Alternatives considered**:
- *Speculatively add OpenAI markers now*: rejected — they don't exist as an API surface; OpenAI's cache is fully automatic. Nothing to add.

### D5 — Snapshot test, not unit test on internals

**Decision**: Add `tests/packages/test_prompt_cache_stability.py` with one test that:
1. Renders `EXTRACT_CACHEABLE_V1` with `(content="...", ask="Q1")` → `parts1`.
2. Renders with `(content="...", ask="Q2")` → `parts2`.
3. Renders with `(content="...", ask="Q3 — long-winded version with extra commas")` → `parts3`.
4. Asserts `parts1.system == parts2.system == parts3.system`.
5. Asserts `parts1.cache_prefix == parts2.cache_prefix == parts3.cache_prefix`.
6. Asserts `parts1.tail != parts2.tail != parts3.tail`.

**Why**: This guards the actual cache contract. Unit tests on `PromptTemplate.render()` internals would tie the test to a specific template body (brittle). The byte-equality assertion is template-agnostic and survives any future template-body edit so long as `{ask}` stays in `tail`.

### D6 — Cost-accounting wiring already exists; no provider code touches it

**Decision**: Leave `extract_token_counts()` and the Anthropic cost-tier math (1.25× write, 0.10× read) unchanged.

**Why**: The infrastructure is already correct (see `providers/anthropic.py:118-132`). The reason cache savings don't appear today is purely upstream — no markers, no cache. Once markers fire, `response.usage.cache_creation_input_tokens` and `response.usage.cache_read_input_tokens` come back populated and the existing math handles the rest.

## Risks / Trade-offs

- **Single-Q sessions cost slightly more.** Cache writes are 1.25× input price. An agent that asks one question on a URL and never returns pays a small premium versus today. **Mitigation**: this access pattern is rare in real agent traces; the multi-Q case dominates. We can monitor `cache_creation_tokens` / `cache_read_tokens` ratio in telemetry and revisit if the write-only pattern proves more common than expected.
- **5-minute TTL is short.** Two questions ten minutes apart yield no cache hit. **Mitigation**: defer extended-cache (1-hour) plumbing; revisit after first production measurement.
- **Anthropic cache requires ~1024+ tokens to be cached.** Very short pages won't benefit. **Mitigation**: these calls are already cheap (sub-cent); no action needed.
- **Page-content byte stability is fragile.** Trafilatura output drift between two fetches (rare, but possible — timestamp watermarks, whitespace) would silently break the cache. **Mitigation**: snapshot test asserts on the render output, not on trafilatura's output. The render is byte-stable by construction. Trafilatura drift is a separate quality-of-extraction concern, not a cache-correctness concern — at worst it produces a cache miss, never a wrong answer.
- **Two cache breakpoints out of 4 used.** If a future change needs more breakpoints (e.g., per-link affordance prompts), we're at 50% budget. Plenty of headroom, but worth tracking.

## Migration Plan

Single PR. Backwards compatible at every call site:

1. Add `EXTRACT_CACHEABLE_V1` template + `PromptParts` type + `PromptTemplate.render()` method. Existing template constants gain `render()` that returns `PromptParts(system="", cache_prefix="", tail=<old user_template formatted>)` — the trivial degenerate shape.
2. Add the dual-block path to `AnthropicProvider.complete()`. Old single-string path remains for any caller passing the old signature.
3. Switch `build_llm_extractor` default to `EXTRACT_CACHEABLE_V1`. WebFetchBaseline + judge templates stay on their existing templates.
4. Add snapshot test.
5. `make check`.

No deprecation cycle needed — the template change is internal, no agent-visible behavior shifts.

## Open Questions

- **None for v1.** Marker on / off, single new template, snapshot test. Affordances and extended-cache TTL are deferred to separate changes.
