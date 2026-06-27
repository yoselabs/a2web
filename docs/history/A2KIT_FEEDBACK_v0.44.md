# a2kit feedback — round 14 (2026-06-28)

> **Status: shipped in a2kit 0.46 (2026-06-28).** `McpConfig.code_mode` landed
> with the tri-state CLI override as asked. a2web adoption: bump to
> `a2kit>=0.46`, set `code_mode=False` in config, verify `list_tools` advertises
> `ask` / `fetch_raw` / `refresh`.

Outgoing wish for the next a2kit minor. Captured from an a2web exploration of
why the installed `a2web serve` MCP surface reaches clients as code-mode
(`search` / `get_schema` / `execute`) rather than as the named `ask` tool. Not
a bug — `code_mode` defaults to `True` and a2web inherited it — but the default
is the wrong fit for a2web's shape, and there is no config seam to override it.

## Expose `code_mode` as an `McpConfig` field, not just a CLI flag

**Ask.** Lift `code_mode` into `McpConfig` as `code_mode: bool = True`, so an App
can declare it once in config. Today it is frozen at
`build_mcp_server(..., code_mode=True)` (`packages/mcp/server.py`) and movable
**only** per-invocation via the `serve --code-mode-off` CLI flag
(`packages/cli/_serve.py` → `mcp_options["code_mode"] = not code_mode_off`) —
there is no config seam. Make the CLI flag a tri-state override: explicit
`--code-mode-off` wins → else `config.mcp.code_mode` → else the function default.

**Why.** `code_mode` is a per-server-*shape* decision — the same category as
`McpConfig.instructions` and `McpConfig.structured_output`, which already live
on that model. The global default (ON) is correct for many-tool / big-payload
servers (a2db, a2atlassian) where the sandbox earns its keep: progressive
schema disclosure across dozens of tools, and keeping large intermediate
payloads out of the calling model's context. It is the wrong default for
a2web's shape — three tools (`ask` / `fetch_raw` / `refresh`), tiny schemas,
payloads already distilled server-side into lean envelopes. There, the sandbox
is pure tax on the ~95% single-`ask` path: an extra `search` / `get_schema`
round-trip, sandbox conventions the caller must get right, and a type-checker
that rejects calls before they run. The context-cost problem code-mode solves
at the orchestration layer, a2web already solved at the payload layer
(server-side Haiku extraction → lean `AskResponse`); running both is
belt-and-suspenders on the common path.

Because there is no config field, a2web's only options to change its own
default are a forgettable per-client `args` flag (`["serve",
"--code-mode-off"]`) repeated in every `~/.claude.json` mount, or argv-munging
in `main()` before `a2kit.run(app)`. Neither is a *declared* default — the
decision wants to live with the App, next to the other `McpConfig` shape knobs.

**a2web's adoption (the bridge).** Once shipped, a2web sets `code_mode=False` in
its own config — one line, no other a2web code change. The
`canonical_name_override` pins on `ask` / `fetch_raw` / `refresh` (already in
`routers.py` for the installed-name MCP contract) finally go live as the
advertised surface, instead of staying dormant behind code-mode's collapsed
`list_tools`. The framework default stays `True`, so a2db / a2atlassian are
untouched — a2web becomes the declared outlier, which matches reality.

**Notes for the a2kit side.**
- The Typer flag needs to become `Optional[bool]` (default `None`) so
  "unspecified" is distinguishable from an explicit `False`; resolution order:
  explicit flag > `config.mcp.code_mode` > built-in `True`. The non-multiplex
  `serve` path also hardcodes `build_mcp_server(app, code_mode=True, ...)`
  (`_serve.py:131`) — that call site needs the same config fallback.
- Additive and back-compatible: no config set and no flag passed = today's
  behavior (`True`).
- `code_mode_allow_destructive` is a separate, security-sensitive knob — leave
  it CLI/operator-only; this ask is only about the `code_mode` on/off default.
