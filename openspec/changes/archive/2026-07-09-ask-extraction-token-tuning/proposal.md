## Why

The `ask` tool leaks two kinds of avoidable token cost on the LLM side of the pipeline: (1) the wire envelope carries a raw, uncurated `meta` dict (every `og:*`/`twitter:*`/`jsonld` tag verbatim) and a `genre` field with no downstream consumer, and (2) the extraction prompt itself has no instruction pushing the model toward token-lean, ASCII-preferring, but fact-lossless output, and no instruction telling it to surface partial signal instead of denying a topic outright when full detail is missing. A live audit (two real `ask` calls against Google Translate UI-change articles) confirmed both: `meta` shipped ~700 chars of dead weight per call, and one call answered "the article does not address camera redesign" when the fetched content actually listed "Camera" as a nav item — a partial-signal miss traceable to the prompt template having no honesty/partial-credit instruction. Tuning this now, purposefully, saves tokens on both the wire (caller cost) and the extraction call (provider cost) without losing any factual content — the floor set by ADR-0009 (never tolerate an unfetched/silently-empty answer) and ADR-0012 (never manufacture a selection) must hold throughout.

## What Changes

- Curate the `meta` field on `AskResponse` to an explicit allowlist of high-value keys (title/description/published-date family) instead of the raw passthrough of every `og:*`/`twitter:*`/`jsonld[0].*` key that `parse_metadata` produces today. `fetch_raw`'s `FetchResponse.meta` is unaffected — it keeps the full raw dict for debug/inspection use.
- (Addendum, post-shipping) Drop `og.site_name` from the allowlist too, leaving `og.description` as the sole allowlisted key — a live sweep of 6 real pages found it always redundant with the domain already visible in the requested URL (see design D6).
- Drop `genre` from the `AskResponse` wire — audit found zero downstream consumers; it is purely descriptive noise. `structural_form`, `shape`, and `obstacle` are kept (each has a real consumer confirmed in the audit).
- Add an explicit token-efficiency instruction to the extraction system prompt(s): be aggressively terse in prose framing, never drop a factual value, identifier, name, number, or unit to save space, and prefer ASCII punctuation over Unicode look-alikes (curly quotes, em dashes, etc.) where meaning is unaffected, since non-ASCII characters can cost more per-token on some tokenizers.
- Add an explicit partial-signal honesty instruction to the router extraction prompt (`EXTRACT_ROUTER_V1`): when the fetched content mentions the asked-about topic but lacks the specific requested detail, the answer must say what IS present rather than asserting the page does not address the topic at all.
- Document (no code change) that provider backend selection is already pluggable via the existing `provider-selection` capability (`claude-code` / `anthropic` / `openai_compatible` — i.e. any OpenAI-compatible LLM), confirming the Claude Code SDK backend option raised in discussion is already first-class and requires no new work here.

## Capabilities

### New Capabilities

(none — this tunes two existing capabilities)

### Modified Capabilities

- `ask-response`: `meta` becomes an explicit allowlisted projection instead of a raw passthrough of every extracted metadata key; `genre` is removed from the wire envelope.
- `extraction`: the LLM extraction prompt templates gain a token-efficiency instruction (terse framing, ASCII-preferring, zero fact loss) and a partial-signal honesty instruction, applied at the prompt-template layer shared by all providers (Anthropic, Claude Code SDK, OpenAI-compatible).

## Impact

- `src/a2web/models.py` (`AskResponse` meta projection, `genre` field removal, associated `_prune_wire` plumbing).
- `src/a2web/packages/llm_extract/prompts.py` (or wherever `EXTRACT_ROUTER_V1` and sibling templates live) — prompt text changes only, no schema/signature change.
- Tests: `tests/capabilities/output_benchmark/` (four-axis harness) should be re-run (`make bench`) after the prompt change per existing CLAUDE.md guidance, since this is exactly the kind of change ("the extraction pipeline... `next_links`") that guidance calls out.
- No MCP tool signature change, no breaking change to `fetch_raw`.
