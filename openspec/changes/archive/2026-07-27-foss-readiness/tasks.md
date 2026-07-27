# Tasks

Docs + metadata only; no `src/` behaviour change. All in-repo, safe to do now.

## 1. License (the missing grant)
- [x] 1.1 Add root `LICENSE` — Apache-2.0 full text, copyright line "Denis
      Tomilin", year. Matches `pyproject.toml` `license = "Apache-2.0"` so
      GitHub's license detector and any consumer see a real grant.
- [x] 1.2 Confirm no conflicting/second license claim anywhere (`pyproject`,
      file headers, README).

## 2. De-personalize CLAUDE.md (genericize in place)
- [x] 2.1 Replace absolute `/Users/iorlas/…` paths with `<repo>` / `$HOME`
      placeholders.
- [x] 2.2 Drop or genericize the private-K pointers (`~/Documents/Knowledge/…`,
      `handover.md`) — either remove or replace with "design notes live with the
      maintainer" so no dead private path ships.
- [x] 2.3 Rewrite the `## Deployment` section: no "Shen", no
      `mcp.shen.iorlas.net`, no personal `~/.claude.json` snippet. Generic:
      build the `Dockerfile` image → publish to a registry → run behind any HTTP
      MCP gateway. Keep `make install-global` as the optional local-dev path.

## 3. Personal-identifier sweep (shipping docs + fixtures)
- [x] 3.1 `README.md`, `docs/adr/*`, `BACKLOG.md`, `CHANGELOG.md`,
      `docs/history/*`, spike notes: remove `Shen` / `iorlas` /
      `mcp.shen.iorlas.net` / absolute home paths. Keep generic "homelab".
- [x] 3.2 eval/benchmark fixtures (`eval/corpus/**/*.http`, committed
      `benchmarks/**` run JSON): strip personal identifiers, or regenerate the
      fixture clean. Confirm none is load-bearing page content before editing.
- [x] 3.3 Leave the two `src/` "homelab" comments as-is (generic; optional reword
      "the homelab workaround" → "a deploy that points browser_robust at
      patchright" for neutrality).

## 4. README as the public front door
- [x] 4.1 What a2web is (one paragraph) + the two tools: `query` (primary,
      server-side LLM extraction, lean envelope) and `fetch_raw` (fallback,
      page-shaped).
- [x] 4.2 Install: git-tag pin **and** `docker pull` the public GHCR image.
- [x] 4.3 60-second quickstart: run the server + one `query` call, expected shape.
- [x] 4.4 Config via `A2WEB_*` (+ optional `$A2WEB_CONFIG` YAML), the secret
      envs (`A2WEB_JINA_KEY`, etc.) as env-only.
- [x] 4.5 Contributor section: `make bootstrap` → `make check` gate; link
      `CONSTITUTION.md` + `docs/architecture/`. License badge/section.

## 5. Secrets audit (confirm-only)
- [x] 5.1 Assert `A2WEB_*` env-only holds — grep tree + `git log -p` spot-check for
      key material / tokens / personal credentials reachable from `main`. Report
      clean or escalate (no history rewrite in this change).

## 6. Optional structural guard (repo philosophy: prevent, don't vigilance)
- [x] 6.1 `tests/architecture/test_no_personal_strings.py`: walk the shipping tree
      (exclude `openspec/changes/archive/**`, `.venv`, regenerable artifacts),
      fail on a denylist (`iorlas`, `mcp.shen.iorlas.net`, `/Users/`). **Anti-
      vacuity floor**: assert it scanned ≥N files, so it can't pass on an empty
      walk (CLAUDE.md "never add a guard that can pass finding nothing").

## 7. Reconcile + close
- [x] 7.1 **Absorb `optional-remote-only-deployment`** (removed as a standalone
      change 2026-07-27 — doc-doctrine only, no capability spec, and mostly
      executed already: local `uv tool uninstall a2web` done; MCP config already
      points at the remote HTTP endpoint; the CLAUDE.md deploy-section reframe
      shipped in `f824ba6`). Its one live remnant folds into task 3 here: grep the
      repo for release steps that assume a local `make install-global` refresh
      (release checklist, CHANGELOG conventions, archived hotfix note) and mark
      `make install-global` opt-in — the canonical deploy is the container image
      run behind an HTTP MCP gateway, not a local binary refresh.
- [x] 7.2 BACKLOG: record "PyPI publish requires shelf packages on PyPI" as the
      deferred distribution follow-up (explicit non-goal of this change).
- [x] 7.3 `make check` green; `openspec validate foss-readiness`.

## 8. Deviations from the plan (recorded, not silent)

- **8.1 The denylist grew one entry the plan did not name: the operator's egress
  IP** (`38.242.156.243`). It appeared in two ADRs and `BACKLOG.md`, and the
  `iorlas`/`Shen`/`/Users/` sweep did not find it — a personal identifier that
  does not look like one. Redacted to "a datacenter IP" (the technical point is
  the ASN class, not the address) and added to the denylist.

- **8.2 The guard reads the GIT INDEX, not the filesystem.** The plan said "walk
  the shipping tree, exclude `.venv` and regenerable artifacts". Walking the
  filesystem immediately produced 40+ false positives from an untracked
  `.hypothesis/` cache full of absolute paths — and every one would have to be
  answered with another skip-list entry. `git ls-files` answers the actual
  question ("what do we distribute") exactly, so untracked local cruft can never
  make the guard red and the exclusion list shrank to three entries that each
  carry a reason.

- **8.3 Exclusion widened from `openspec/changes/archive/**` to
  `openspec/changes/**`.** A change that *proposes removing* an identifier has to
  be able to name it — this very change's `proposal.md` would have failed the
  guard it adds. `openspec/specs/**`, the durable spec, is still scanned.

- **8.4 Fixture hits were confirmed as page content and deliberately NOT edited.**
  Every `Shen` match in `benchmarks/**` and `eval/corpus/**` is a real captured
  page: an academic author (Yikang Shen) in a Wikipedia citation, and GitHub
  usernames. Editing a frozen capture to satisfy a lint corrupts the thing under
  test. This is why the denylist is composed of unambiguous IDENTIFIERS rather
  than names — a bare surname cannot be told apart from page content.

- **8.5 The `surface_eval_v2` leak detector was parameterized, not stripped.** It
  greps extraction output for the operator's name/handle to prove the model
  answered from the PAGE and not from anything it knows about the person asking —
  so the personal terms there were load-bearing test data, not a leak. Deleting
  them would have quietly weakened a real check. The operator-specific half now
  reads `A2WEB_LEAK_TERMS` from the environment; the generic phrase patterns stay
  hardcoded.

- **8.6 README staleness was a bigger job than "presentation".** It documented a
  retired framework (`a2kit`), the pre-rename `ask` tool, `uv tool install a2web`
  against a package that is not on PyPI, dropped CLI commands (`list-tools`,
  `schema`), a gated-off browser engine (Camoufox), and a dead env var
  (`A2KIT_MCP__CODE_MODE`). Corrected against the live CLI and the manifests
  rather than from memory. One correction was not cosmetic: the benchmark section
  claimed a fallback from the subscription provider to the metered Anthropic API,
  which ADR-0016 explicitly forbids — following that README would have produced a
  surprise bill.

- **8.7 NOT done — an intermittent test failure was observed and is unresolved.**
  `tests/eval_replay/test_regression_corpus.py::test_regression_replay[akakce-cloudflare-bot-wall]`
  failed twice under `make check` today and passes 3/3 on a full standalone run
  and every time in isolation. It is unrelated to this change (docs + one new
  test file; that case never calls the extractor). Recorded in `BACKLOG.md`
  rather than dismissed as noise — an intermittent failure nobody wrote down is
  how a real bug becomes "that test is flaky".
