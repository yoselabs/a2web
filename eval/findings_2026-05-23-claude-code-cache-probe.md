# Claude Code SDK cache-behaviour probe — 2026-05-23

**Spike**: `eval/spikes/claude_code_cache_probe.py`
**Model**: `claude-haiku-4-5`
**Template**: `EXTRACT_CACHEABLE_V1` (v0.19 production default)
**Provider**: `ClaudeCodeProvider` (piggybacks the `claude` CLI's OS session)

## Question

Does the Claude CLI binary auto-cache our byte-stable prefix when we send different `{ask}` values over the same `{content}` via `claude-agent-sdk`?

## Method

Five calls, varying page and question:

| call | page | ask                                              |
|------|------|--------------------------------------------------|
| 1    | A    | "What is the population of Tristan da Cunha?"    |
| 2    | A    | "What is the climate like?"                      |
| 3    | B    | "What is the climate like?"                      |
| 4    | A    | "What happened in 1961?"                         |
| 5    | A    | "What is the population of Tristan da Cunha?"    |

Page A: ~5 KB about Tristan da Cunha. Page B: ~2 KB about Guatemalan coffee. Inter-call gap: 200 ms (well within 5-minute TTL).

## Raw results

| call | page | prompt_tok | cache_read | cache_create | latency_ms | cost_usd |
|------|------|-----------:|-----------:|-------------:|-----------:|---------:|
| 1    | A    | 41 286     | 0          | 41 284       | 12 150     | $0.0520  |
| 2    | A    | 41 279     | **26 822** | 14 455       | 8 756      | $0.0210  |
| 3    | B    | 40 946     | **26 822** | 14 122       | 8 980      | $0.0208  |
| 4    | A    | 41 280     | **26 822** | 14 456       | 8 928      | $0.0215  |
| 5    | A    | 41 286     | **41 284** | 0            | 8 520      | $0.0043  |

## Finding (surprise inside)

**The CLI auto-caches — but NOT our prefix.** Three structural observations:

1. **The cache_read value is 26 822 on calls 2, 3, AND 4** — identical across same-page (A) and different-page (B) calls. If the cache hit were keyed on our `{content}` prefix, call 3 (different page B) should have read **zero** from cache. It didn't.

2. **The 26 822 tokens are Claude Code's own preset / system / tools / skills overhead** — stable across every call regardless of what we send. The CLI writes this to cache on call 1 (where cache_creation = 41 284 = the WHOLE prompt) and reads it back on every subsequent call.

3. **Call 5 (exact repeat of call 1) reads 41 284 tokens from cache, writes zero.** So the CLI does cache the entire user message as a single block — but it hits only on **byte-exact full-message repeats**, not on prefix matches with different tails.

### Decomposition

For Page A calls 2/3/4, the math works out as:

```
prompt_tokens = fresh + cache_read + cache_creation
~41 280       = ~3    + 26 822     + ~14 455
```

- ~26 822 tokens — Claude Code preset (always cached after warmup)
- ~14 455 tokens — our page+question (newly cache-written EACH time, not read from cache)
- ~3 tokens — small per-call delta

So the CLI **does not apply cache_control breakpoints inside our user message**. It treats the whole user content as one cache block, keyed on the full byte string.

## Cost picture

| pattern                                | cost      | vs cold       |
|----------------------------------------|----------:|--------------:|
| Cold (call 1)                          | $0.0520   | baseline      |
| Same page + different ask (calls 2-4)  | ~$0.0211  | **−60%**      |
| Exact repeat (call 5)                  | $0.0043   | **−92%**      |

The 60% reduction on different-ask calls comes entirely from Claude Code's auto-cached preset — **not from our prefix discipline**. Our byte-stable `cache_prefix` does nothing here.

The 92% reduction on exact repeats happens, but that's the access pattern our sqlite `ExtractionCache` (layer 2) already covers — so production code would have short-circuited before reaching the SDK.

## What this means for v0.19

The v0.19 `EXTRACT_CACHEABLE_V1` template + byte-stable-prefix discipline:

- **Direct `AnthropicProvider`**: works as designed. Explicit `cache_control` markers on system + first user block fire prefix-based cache hits on different-ask-same-page calls. Expected ~60-70% savings on long-page extraction.
- **`ClaudeCodeProvider` (CLI path)**: gets ~60% savings on different-ask-same-page calls, **but from the CLI's preset caching**, NOT from our prefix work. The byte-stable prefix is essentially a no-op on this path — page content gets re-written to cache on each new question.

**Implication**: production users running on Claude Code OAuth sessions get reasonable caching for free (the CLI handles it), but they do not benefit from our v0.19 prefix work specifically. Users with `ANTHROPIC_API_KEY` set get the full prefix-based win.

## Follow-ups

- 🟡 **Investigate whether `claude` CLI exposes a flag/env var to opt into multi-breakpoint caching** for one-shot `query()` calls. If `--cache-prefix=...` or similar exists, we may be able to tell the CLI where to put a second breakpoint. Quick `claude --help` walkthrough warranted.
- 🟡 **Consider preferring `AnthropicProvider` when both keys are available.** Today `LlmExtractorResource` falls back to claude_code when `ANTHROPIC_API_KEY` is missing. Worth measuring: on a multi-Q corpus run, is the AnthropicProvider+markers cost lower than ClaudeCodeProvider+CLI-cache? The 60% vs 70% gap may or may not justify a key-rotation rebalance.
- 🟢 **Telemetry**: surface cache_read / cache_creation breakdown on the LDD bus so production can replicate this measurement at scale.
- 🟢 **The byte-stable prefix is still load-bearing for OpenAI** (auto-prefix-cache, prefix-keyed). Don't undo the template reshape.

## Caveats

- Single session, 5 calls. Larger N would tighten the cost numbers.
- Page A ~5 KB; page B ~2 KB. Larger pages would amplify the difference between "page cached" and "preset cached" scenarios.
- 200 ms inter-call gap; TTL not stressed.
- Test ran against a logged-in Claude Code session — costs reflect the OAuth subscription's billing (or lack thereof). Token counts are real; dollar figures are list-price reconstruction.
