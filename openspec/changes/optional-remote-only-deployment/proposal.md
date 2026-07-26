## Why

a2web's documented deployment model makes the local machine the primary host: it
is installed as a `uv tool` at `~/.local/bin/a2web`, wired into Claude Code's MCP
config (`~/.claude.json` → `mcpServers.a2web` → the local binary, `args:["serve"]`),
and `make install-global` is described as **mandatory** after every version bump so
the local session picks up new code.

That is no longer how the operator runs it. a2web is deployed remotely on the
homelab (the Shen gateway, reachable as the `Shen` MCP server with
`a2web_query` / `a2web_fetch_raw` tools) and will always be produced remotely from
here on. The local install is now pure liability: a stale second copy that has to
be manually refreshed, an extra binary on the PC, and a `~/.claude.json` entry
pointing at code that drifts behind `main`.

## What Changes

- **`make install-global` becomes explicitly OPTIONAL.** Reframe it in `CLAUDE.md`
  ("Global install" + the `make install-global` guidance) from "mandatory after a
  bump" to "optional local-serve convenience"; the canonical deployment is the
  remote homelab/Shen container built from `container-image`.
- **Remove the local a2web install** (`uv tool uninstall a2web`) and the
  `~/.claude.json` `mcpServers.a2web` local-binary entry. The remote `Shen` MCP
  server already provides the tools.
- **Sever the local-refresh assumption** wherever docs tie a release to a
  `make install-global` step (e.g. the archived hotfix note, release checklist):
  a release ships the container; local refresh is opt-in only.

## Impact

- The local uninstall + `~/.claude.json` edit are **environment mutations on the
  operator's machine** — performed deliberately outside explore mode, with the
  operator confirming the remote `Shen` server answers first so there is no gap.
- No `src/` change; `make install-global` and the `[project.scripts]` entrypoint
  stay available for anyone who does want a local serve.
- Non-goal: removing the CLI or the stdio entrypoint — only the *mandatory local
  install* doctrine and the operator's specific local copy.
