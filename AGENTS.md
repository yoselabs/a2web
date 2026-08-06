# Agent Instructions

> Read `CONSTITUTION.md` first — substrate/product placement, dependency
> adoption, magic budget. Phase A: agents apply, human confirms
> Constitution-touching changes.

This project uses **bd** (beads) for issue tracking — `bd prime` for full
workflow context. See [SYNC_CONCEPTS.md](https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md)
for sync anti-patterns (don't treat JSONL as source of truth, don't `bd
import` during normal operation).

## Shelf

- Shared substrate: `github.com/yoselabs/shelf`, pinned in `pyproject.toml` by tag. Adopt only if **DEEP · STABLE · WINS**; contribute back by promotion.
- Resolve the loop lazily, once per session, first time you touch it — never at startup. Read `<shelf>/docs/agent-loop.md` from `$SHELF_HOME` → `../shelf` → `~/Workspaces/shelf` (clone once if absent).
- Never hit GitHub at session start. Never commit a local `path=`/editable shelf source (`tests/architecture/test_no_local_shelf_source.py`).

## Architecture

MCP/CLI server fetching web content adaptively, on `fastmcp` (>=3.4) directly — a2kit retired 2026-07-22, see `openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/design.md` before touching composition/wire/errors.

- Composition root: `components.build_components()` — frozen dataclass of `Lazy[T]` thunks (shelf `async_scope`); `ResourceScope` unwinds LIFO from the FastMCP `lifespan=` exit. Cold-start laziness / single-composition-root are architecture-tested (`tests/architecture/test_cold_start_laziness.py`, `tests/architecture/test_one_composition_root.py`).
- Module map, one file per pipeline area (`docs/architecture/README.md` has the full list): `composition-and-entrypoints.md`, `wire-and-errors.md`, `api-surface.md`, `fetcher-pipeline.md`, `resources-and-events.md`, `packages-and-plugins.md`.
- Handlers, **Nine:** `arxiv.py`, `discourse.py`, `github.py`, `habr.py`, `hn.py`, `reddit.py`, `twitter.py`, `v2ex.py`, `wikipedia.py` (`src/a2web/handlers/`).
- Tiers, `tiers/` (8 tiers — `archive`, `browser`, `browser_robust`, `firecrawl`, `jina`, `raw`, `site_handler`, `zyte`), each a `_manifests/tiers/<name>.py`.

## Testing

- Seam: `tests/_helpers/mcp.py` — `mcp_client(components=parts)` drives a real `fastmcp.Client`, nothing faked.
- `call_wire` = `structured_content` JSON. `call_text` = `content[0].text` (adds TSV blocks). Assert on `call_text` when the agent's own view is the point.
- Fakes: `dataclasses.replace(parts, llm_extractor=lazy(fake))` — errors loudly on a field that no longer exists.
- CLI contract: `tests/contracts/cli/*.json`; deltas from the frozen capture must be named in `_ACCEPTED` with a reason.
- `@pytest.mark.protects(...)` — optional, names what a test protects using an
  identifier that already exists: `spec:<capability>` + quoted `Requirement: <heading>`,
  `adr:<NNNN>`, or `change:<change-id>`. A declared id must resolve or the suite fails
  (`make recon-check`). Never invent a new identifier to satisfy this — copy one you
  already hold. See `openspec/changes/bind-tests-to-requirements/specs/spec-test-traceability/spec.md`.

## Dev Commands

`make check` (lint + ty + test, coverage ≥85%) / `lint` / `fix` / `ty` / `test` / `dev` / `bootstrap` / `bench` / `install-global` / `recon` (spec↔test report, read-only) / `recon-check` (same, as a pass/fail gate — not in `make check`).

## Enforcement

`make check` via `.github/workflows/ci.yml` — every push/branch/PR. Does not itself block a merge (a GitHub branch-protection setting); `fb:no-prs` means merges go direct to `main`. `release.yml` reruns `make check` + `make test-browser` on every `v*` tag (publishes the image). `.pre-commit-config.yaml` is opt-in locally, lint only.

## Deployment

Remote container over HTTP is canonical, not a local binary. `Dockerfile`'s `INSTALL_BROWSER` defaults `false` (~390MB browserless); `release.yml` passes `true` — published image carries the browser (patchright+zendriver+Chromium, ~1.35GB of ~1.9GB). Pinned: `tests/capabilities/endpoint_auth/test_container_browser_arg.py`. `[cookies]`/`[claude-code]` extras dropped from the container. Browserless degrades loudly via the ADR-0009 envelope; Zyte/Firecrawl still cover hard sites. `make install-global` is local-only, not part of the deploy path.

## Benchmark

`make bench` (`src/a2web/llm_eval/`, corpus `eval/corpus.yaml`) is live-network and spends LLM quota — NOT in `make check`. Run after a change to envelope shape / extraction / tier routing / handlers / `next_links`. Capture every new failure or edge case in `eval/corpus.yaml` the SAME session, phrased against stable structural facts.

## Conventions

- `dataclass(slots=True)` internal; pydantic at API boundaries. `asyncio.to_thread` chokepoint per sync module (Ruff `ASYNC100/210/230` enforces).
- Heavy/conditional resources are `Lazy[T]` thunks on `Components`, passed down UNAWAITED. Named factory in `state.py`, wired in `components.py` — those two modules only.
- Events: `await a2web.log.info(PayloadType(...))` (async, keep the `await`). Phases never accept or pass `ctx`.
- One logger, `a2web` (`propagate=False` + NullHandler floor — MCP is stdio). No bare `structlog`.
- `purgatory` for circuit breakers. Closed-enum verdicts. `fmt_dur(ms)` for durations. Tools never return `-> str` — dict/pydantic model, module scope only.

## Architecture invariants

`tach.toml` (module boundaries) + `tests/architecture/` (AST call-site/signature/class-shape rules). Registry + workflow for adding a rule: `docs/architecture/README.md`.

## Never

- Never commit credentials — secrets are env-only (`A2WEB_*`).
- Never cache a page that fails the quality gate — block pages must never enter cache.
- Never tolerate an unfetched URL — a failed fetch ships `status: failed` + `retrieval_incomplete` + a critical `try_user_browser` hint (`docs/adr/0009-never-silently-miss-a-url.md`).
- Never manufacture a selection — relay content, never rank/filter/crown by a2web's own criterion (`docs/adr/0012-shape-and-relay-never-manufacture-a-selection.md`).
- Never surface a URL not on the page — every emitted URL traces to a `{{n}}` digest handle or literal page content, never pattern-guessed (`docs/adr/0014-grounded-urls-only-off-domain-flagged.md`).
- Never withhold the body without leaving the index — `also_here` + `other_pages` cover what `query` didn't surface (`docs/adr/0015-the-withheld-body-index.md`).
- Never assert a wall on evidence-free thinness, never promote an unverified empty to `ok` — ambiguous cases err toward the wall side; a promoted empty is wire-only, never cached.
- Never bill the metered Anthropic API in dev/eval/bench — subscription providers only, guarded by `anyllm.cost.with_cost_guard` (`docs/adr/0016-never-metered-api-in-dev-loop.md`).
- Never retry the whole flow — retries live at one of 5 layers (connection/HTTP/proxy/tier/handler) with circuit breakers.
- Never add an unbounded wait, never bound it per-call-site — three seams own it: `settings.request_timeout`, `llm_resource.TimeoutProvider`, `fetcher._within_budget`.
- Never let a recursive renderer walk untrusted input unbounded — cap depth + a shared node budget, declare the truncation (`tests/architecture/test_recursive_renderers_are_bounded.py`).
- Never add `print()` or sync I/O in async paths.
- Never let a later stage discard a producer's own claim — ADD to an index, never silently replace or relabel it.
- Never declare a truncation against a number that cannot differ — read the SOURCE-stated total.
- Never reintroduce `tier_extras: dict[str, Any]` — typed field on `TierResult` instead.
- Never bypass `Lazy[T]` at the tool seam — pass the thunk down, unwrap once (`tests/architecture/test_cold_start_laziness.py`).
- Never build the resource graph outside `components.build_components()` (`tests/architecture/test_one_composition_root.py`).
- Never pass `ctx` to a phase function — `a2web.log` forwards to the MCP wire only under a dispatch scope.
- Never re-derive the TSV field list from model introspection (`wire._TSV_FIELDS` is literal); never let `encode_envelope` resurrect a pruned field or re-encode an already-encoded string; never let a TSV table's columns come from one row — UNION of every row's keys, via `wire.encode_rows`.
- Never let a handler report walled content as `ok` — call `challenge_verdict` before extracting prose (`tests/architecture/test_handler_challenge_check.py`).
- Never let a degraded sub-fetch render as absent-at-source — mark the section, emit `section_unretrieved`.
- Never let a CLI command return without unwinding its `ResourceScope` — an unclosed scope hangs the process.
- Never allowlist a guard to expect nothing on an unverified claim — assert the thing is PRESENT and constructible. Never add a structural guard without a non-vacuity floor.
- Never let a hand-written fixture be the oracle for parser-matches-live-site — fixtures are CAPTURED (`tests/fixtures/captured/`). Never treat a golden as proof of correctness — it proves unchanged, not correct.

Dated incident narrative behind these rules: `docs/findings/2026-08-06-claude-md-decomposition-history.md`.

## Backlog

`bd` tracks deferred work. Real blocker → `bd dep add <id> <blocker> --type blocks`. Shelved, nothing specific blocking → `bd defer <id> --reason "..."`. Blocked on something with no bead → manual `--status blocked` + comment (never a synthetic blocker for "not started yet" — that's `deferred`). Link a bead to its OpenSpec change via `bd update <id> --spec-id "..."`. Narrative/evidence lives in `docs/findings/`, not in a bead body.

## Ask First

Before: changing tool signatures; adding top-level deps; changing the response envelope shape; a new tier/handler outside Strategy+Registry; reintroducing a `dict[str, Any]` pipeline bag; promoting a module to `packages/`.

## Shell Commands

Non-interactive flags only — some shells alias `cp`/`mv`/`rm` to `-i`, which hangs an agent on a y/n prompt. Use `cp -f`, `mv -f`, `rm -rf`. Also: `ssh`/`scp -o BatchMode=yes`, `apt-get -y`, `brew` with `HOMEBREW_NO_AUTO_UPDATE=1`.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:970c3bf2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

**Override (authorized deviation from the block above, `adopt-beads-work-queue` D7):**
`bd remember`/`bd prime` are NOT adopted for persistent knowledge in this repo — Denis
already runs three memory systems outside this repo, and a fourth here would fragment
them. Use `bd` for issue tracking only (create/update/close/comment/dep). Continue using
this repo's own `AGENTS.md`/`docs/`/`docs/findings/` for durable knowledge, exactly as
before bd was adopted.

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
