# Tasks

## 1. Doctrine (in-repo, safe to do now)
- [ ] 1.1 `CLAUDE.md` "Global install": reframe `make install-global` from
      mandatory-after-bump to optional local-serve convenience; state the
      canonical deployment is the remote homelab/Shen container.
- [ ] 1.2 Grep the repo for release steps that assume a local refresh
      (release checklist, CHANGELOG conventions) and mark `make install-global`
      opt-in.

## 2. Operator environment (deliberate, OUTSIDE explore mode, confirm-gated)
- [ ] 2.1 Confirm the remote `Shen` MCP server answers `a2web_query` /
      `a2web_fetch_raw` — no coverage gap before removing the local copy.
- [ ] 2.2 `uv tool uninstall a2web`.
- [ ] 2.3 Remove `mcpServers.a2web` (local-binary entry) from `~/.claude.json`.
- [ ] 2.4 Verify a fresh Claude Code session resolves a2web tools via `Shen` only.

## 3. Close
- [ ] 3.1 `make check` green (doc-only in-repo change).
