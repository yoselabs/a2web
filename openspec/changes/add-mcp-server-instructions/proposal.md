## Why

ADR-0009 already pushed a2web-side hint wording to its ceiling: `try_user_browser_hint` carries `severity: critical` and imperative text ("You MUST... do not answer as if you do"), yet a real session still missed it — the calling agent tried one browser tool, generalized its failure to "no browser available," and never revisited the hint against a second, unused browser tool. The hint text was already maximally loud; the miss was an attention failure, not a legibility failure, because that text arrives buried inside a tool-result JSON blob competing with everything else in context by the time it matters. ADR-0009 itself names the ceiling: "a2web cannot force the downstream agent to obey." The MCP protocol's `InitializeResult.instructions` field is one layer up from hint text that a2web has never used — a short string injected into the calling agent's context declaratively at connection, before any tool call, the same mechanism already observed working for other MCP servers in this environment.

## What Changes

- Set `instructions=` on the `FastMCP(name="a2web", ...)` construction in `src/a2web/server.py`, currently unset.
- The instructions string names ONE specific, previously-unaddressed failure mode — stopping after the first browser tool tried — rather than restating what `try_user_browser_hint`'s own `fix` field already says. It is a standing per-connection cost (paid whether or not a wall is ever hit), so it stays aggressively terse (target ~25 tokens).
- No change to any hint's wording, the envelope shape, or fetch/retrieval logic.

## Capabilities

### New Capabilities
- `mcp-server-instructions`: the a2web MCP server declares a short `instructions` string at connection time (MCP `initialize` handshake) directing any calling agent to check every available browser tool — not just the first — before treating a `severity: critical` operator hint's URL as unreachable.

### Modified Capabilities
(none — `retrieval-completeness` and `app-composition` are unchanged; this adds a new, separate signal rather than altering what a2web computes or emits per-fetch)

## Impact

- `src/a2web/server.py` — one added constructor kwarg.
- No wire/envelope change, no new `HINT_CODES` entry, no test-contract capture change expected (the `initialize` handshake is outside `tests/contracts/cli/*.json`'s CLI-invocation scope).
- Verified during exploration (not yet re-verified inside this change): `instructions` is protocol-level (`mcp/types.py:698`), FastMCP's constructor accepts it (`fastmcp/server/server.py:324`), and Claude Code surfaces it (confirmed empirically this session via "claude-in-chrome" and "qmd" instructions). Claude Desktop's rendering of this field was not independently verified — greenlit anyway on Claude Code evidence per explicit user decision.
