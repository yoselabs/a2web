# Tasks

Docs + metadata only; no `src/` behaviour change. All in-repo, safe to do now.

## 1. License (the missing grant)
- [ ] 1.1 Add root `LICENSE` — Apache-2.0 full text, copyright line "Denis
      Tomilin", year. Matches `pyproject.toml` `license = "Apache-2.0"` so
      GitHub's license detector and any consumer see a real grant.
- [ ] 1.2 Confirm no conflicting/second license claim anywhere (`pyproject`,
      file headers, README).

## 2. De-personalize CLAUDE.md (genericize in place)
- [ ] 2.1 Replace absolute `/Users/iorlas/…` paths with `<repo>` / `$HOME`
      placeholders.
- [ ] 2.2 Drop or genericize the private-K pointers (`~/Documents/Knowledge/…`,
      `handover.md`) — either remove or replace with "design notes live with the
      maintainer" so no dead private path ships.
- [ ] 2.3 Rewrite the `## Deployment` section: no "Shen", no
      `mcp.shen.iorlas.net`, no personal `~/.claude.json` snippet. Generic:
      build the `Dockerfile` image → publish to a registry → run behind any HTTP
      MCP gateway. Keep `make install-global` as the optional local-dev path.

## 3. Personal-identifier sweep (shipping docs + fixtures)
- [ ] 3.1 `README.md`, `docs/adr/*`, `BACKLOG.md`, `CHANGELOG.md`,
      `docs/history/*`, spike notes: remove `Shen` / `iorlas` /
      `mcp.shen.iorlas.net` / absolute home paths. Keep generic "homelab".
- [ ] 3.2 eval/benchmark fixtures (`eval/corpus/**/*.http`, committed
      `benchmarks/**` run JSON): strip personal identifiers, or regenerate the
      fixture clean. Confirm none is load-bearing page content before editing.
- [ ] 3.3 Leave the two `src/` "homelab" comments as-is (generic; optional reword
      "the homelab workaround" → "a deploy that points browser_robust at
      patchright" for neutrality).

## 4. README as the public front door
- [ ] 4.1 What a2web is (one paragraph) + the two tools: `query` (primary,
      server-side LLM extraction, lean envelope) and `fetch_raw` (fallback,
      page-shaped).
- [ ] 4.2 Install: git-tag pin **and** `docker pull` the public GHCR image.
- [ ] 4.3 60-second quickstart: run the server + one `query` call, expected shape.
- [ ] 4.4 Config via `A2WEB_*` (+ optional `$A2WEB_CONFIG` YAML), the secret
      envs (`A2WEB_JINA_KEY`, etc.) as env-only.
- [ ] 4.5 Contributor section: `make bootstrap` → `make check` gate; link
      `CONSTITUTION.md` + `docs/architecture/`. License badge/section.

## 5. Secrets audit (confirm-only)
- [ ] 5.1 Assert `A2WEB_*` env-only holds — grep tree + `git log -p` spot-check for
      key material / tokens / personal credentials reachable from `main`. Report
      clean or escalate (no history rewrite in this change).

## 6. Optional structural guard (repo philosophy: prevent, don't vigilance)
- [ ] 6.1 `tests/architecture/test_no_personal_strings.py`: walk the shipping tree
      (exclude `openspec/changes/archive/**`, `.venv`, regenerable artifacts),
      fail on a denylist (`iorlas`, `mcp.shen.iorlas.net`, `/Users/`). **Anti-
      vacuity floor**: assert it scanned ≥N files, so it can't pass on an empty
      walk (CLAUDE.md "never add a guard that can pass finding nothing").

## 7. Reconcile + close
- [ ] 7.1 **Absorb `optional-remote-only-deployment`** (removed as a standalone
      change 2026-07-27 — doc-doctrine only, no capability spec, and mostly
      executed already: local `uv tool uninstall a2web` done; MCP config already
      points at the remote HTTP endpoint; the CLAUDE.md deploy-section reframe
      shipped in `f824ba6`). Its one live remnant folds into task 3 here: grep the
      repo for release steps that assume a local `make install-global` refresh
      (release checklist, CHANGELOG conventions, archived hotfix note) and mark
      `make install-global` opt-in — the canonical deploy is the container image
      run behind an HTTP MCP gateway, not a local binary refresh.
- [ ] 7.2 BACKLOG: record "PyPI publish requires shelf packages on PyPI" as the
      deferred distribution follow-up (explicit non-goal of this change).
- [ ] 7.3 `make check` green; `openspec validate foss-readiness`.
