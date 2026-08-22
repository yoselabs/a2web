## Context

See `proposal.md` - Why. `src/a2web/server.py:94` constructs `FastMCP(name="a2web", **fastmcp_kwargs)` with no `instructions=`. `fastmcp_kwargs` is assembled earlier in the same function from settings; the new string is a static constant, not settings-derived, so it does not need a new `AppSettings` field.

## Goals / Non-Goals

**Goals:**
- Add exactly one `instructions=` string, sourced from a single named constant (mirroring how `hints.py` centralizes hint copy — this is also load-bearing agent-facing copy, not incidental).
- Keep the string under ~30 tokens; every added word is a standing per-connection cost.

**Non-Goals:**
- Does not change `try_user_browser_hint` or any other hint's wording, code, or severity.
- Does not attempt the "force a human checkpoint on skip" scenario raised alongside this one during exploration — that is a caller-side policy question (the consuming agent's own CLAUDE.md/AGENTS.md), not something the MCP `instructions` field or any other a2web-side mechanism can compel.
- Does not add a `doctor`-style coverage report for ignored critical hints (flagged in ADR-0009 as a possible future enforcement layer, but out of scope here).

## Decisions

**Where the constant lives**: a module-level constant near the `FastMCP(...)` call in `server.py`, not in `hints.py`. `hints.py`'s own docstring scopes it to `OperatorHint` factories reached through the closed `HINT_CODES` vocabulary; `instructions` is a different wire surface (the `initialize` handshake, not a tool-result field) and doesn't belong in a catalogue whose guards (`test_every_hint_code_has_a_factory.py`) are keyed to `HINT_CODES`.

**Content**: names the one gap per-hint text doesn't cover — stopping after the first browser tool — rather than re-explaining what `critical` means or repeating `try_user_browser_hint`'s own `fix`. Draft, ~25 tokens:

> `a2web severity:"critical" hint: try every available browser tool (not just the first) before treating the URL as unreachable.`

**No settings/config knob**: unlike `feedback_enabled` (`register_feedback_tools`), this isn't optional or endpoint-dependent — it's static guidance with no credentials or external service involved, so a toggle would only add surface for no behavioral benefit.

## Risks / Trade-offs

- [Standing token cost on every session, whether or not a wall is ever hit] → mitigated by keeping the string terse and single-purpose (see Decisions); if usage data later shows sessions rarely hit critical hints, revisit length or existence.
- [Client support varies — confirmed in Claude Code this session, unverified in Claude Desktop] → the field is protocol-level (`mcp/types.py:698`) so a client that ignores it simply drops it silently; no failure mode, only reduced benefit on unsupported clients. Not a blocker per explicit user decision.
- [Future hint-copy edits could drift out of sync with the instructions string's claim about what `fix` says] → low risk since the instructions string deliberately avoids quoting or paraphrasing any specific hint's `fix` text.
