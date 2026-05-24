# Claude Code CLI flag sweep — 2026-05-24

**Follow-up to**: `eval/findings_2026-05-23-claude-code-cache-probe.md`
**Spike**: `eval/spikes/claude_code_cache_bare.py`
**Model**: `claude-haiku-4-5`

## Question

The 2026-05-23 probe found ~26 822 tokens of overhead per call (visible as
the cache_read plateau on calls 2/3/4) that we hypothesised was Claude
Code's own preset / auto-discovery / skill / hook envelope. Can we
opt out of it via SDK options?

## Flags surveyed

`claude --help` exposes several flags reachable via
`ClaudeAgentOptions.extra_args` or named fields:

| flag                                          | effect                                                 | viable for our path? |
|-----------------------------------------------|--------------------------------------------------------|----------------------|
| `--bare`                                      | strip hooks/LSP/plugin sync/auto-memory/keychain/etc.  | ❌ requires ANTHROPIC_API_KEY; kills OAuth |
| `--exclude-dynamic-system-prompt-sections`    | move per-machine bits to user message → cache reuse    | ❌ only applies with default system prompt; we override |
| `setting_sources=[]`                          | skip user/project/local settings (CLAUDE.md discovery) | ✅ |
| `skills=[]`                                   | don't load skill registry                              | ✅ |
| `extra_args={"disable-slash-commands": None}` | skip slash command pre-registration                    | ✅ |

## Result

Combined opt-out (`setting_sources=[] + skills=[] + --disable-slash-commands`):

| call           | baseline prompt | optimized prompt | Δ        | baseline cache_read | optimized cache_read | baseline cost | optimized cost |
|----------------|---------------:|-----------------:|---------:|--------------------:|---------------------:|--------------:|---------------:|
| call_1 (A/Q1)  | 41 286         | **18 731**       | −22 555  | 0                   | 0                    | $0.0520       | $0.0244        |
| call_2 (A/Q2)  | 41 279         | **18 724**       | −22 555  | 26 822              | 13 286               | $0.0210       | $0.0092        |
| call_3 (B/Q2)  | 40 946         | **18 497**       | −22 449  | 26 822              | 13 286               | $0.0208       | $0.0090        |
| call_4 (A/Q3)  | 41 280         | **14 257**       | −27 023  | 26 822              | 0                    | $0.0215       | $0.0190        |
| call_5 (A/Q1)  | 41 286         | **14 263**       | −27 023  | 41 284              | 9 016                | $0.0043       | $0.0084        |
| **session $**  |                |                  |          |                     |                      | **$0.1196**   | **$0.0700**    |

**Net: ~41% session cost reduction, ~22-27k tokens off every call.**

## Sub-finding worth following

Calls 4 and 5 shed an additional ~4k vs calls 2 and 3 (18.7k → 14.2k)
mid-session. Some CLI warmup state collapses further after a few calls.
Cache behaviour is also noisier: call 4's prefix lookup misses entirely
(cache_read=0) and call 5's exact-repeat reads only 9k (vs 18k of prompt).

Not blocking the headline win, but worth investigating before relying on
the byte-stable prefix discipline being load-bearing on this path.

## Recommendation

Apply the three opt-outs to `ClaudeCodeProvider` unconditionally:

```python
options_kwargs: dict[str, Any] = {
    "model": model,
    "tools": [],
    "max_turns": 1,
    "max_thinking_tokens": 0 if thinking_disabled else None,
    "system_prompt": system_str,
    "setting_sources": [],          # NEW — skip CLAUDE.md / settings discovery
    "skills": [],                   # NEW — skip skill registry
    "extra_args": {"disable-slash-commands": None},  # NEW
}
```

Three new attributes on the options dataclass, one new `extra_args` flag.
No public API change. Backwards-compatible with users on older SDK
versions only if they're on a version that accepts those kwargs (the
provider's import is already pinned to a recent SDK in `pyproject.toml`).

Risk: the opt-out shrinks the per-call envelope to a base that we don't
directly control. If the CLI ever bundles user-relevant context into one
of the dropped surfaces (e.g., a project-level setting that affects
output formatting), we'd silently lose it. For an extraction call (text
in / text out, tools disabled, single turn), this risk is minimal.

## Costs caveat

Token counts and dollar figures are reconstructed from
`ResultMessage.total_cost_usd` and `ResultMessage.usage`. Users on
Claude Code OAuth subscriptions see no direct billing impact; the dollar
figures are list-price reconstruction. Token reduction is real and will
matter on `ANTHROPIC_API_KEY`-routed paths.
