## Why

`BACKLOG.md` (2796 lines, 71 `## ` headings) and `BACKLOG-CLOSED.md` (852
lines, 20 headings) are a flat-file queue with no dependency graph, no atomic
claim, and no per-worktree visibility — every agent reads the same 3648 lines
of prose to find what to work on, and two agents in two worktrees editing the
file at once produce a merge conflict on prose, not on data.

**Beads (`bd`) replaces the file with a graph:** issue data lives in an
embedded Dolt DB (`.beads/embeddeddolt/`, gitignored), synced via
`bd dolt push`/`pull` against `refs/dolt/data` — a ref namespace orthogonal to
`refs/heads/*`, so it doesn't conflict with code branches. Confirmed via
`docs/reference/worktrees.md` and `docs/reference/git-integration.md` (not
assumed): every worktree of one clone auto-discovers and shares the same
`.beads` workspace, with no per-worktree duplication. That is the concrete
capability BACKLOG.md cannot offer no matter how it's reorganized.

**This needs a proposal, not a `git rm`, for one reason:** `grep -rIo
'BACKLOG[A-Z-]*\.md' --exclude-dir=.git .` finds 165 textual references across
~20 tracked files, including `CONSTITUTION.md`, `tach.toml`, `Makefile`,
`.pre-commit-config.yaml`, and 6 `src/` comments. Most are frozen historical
record and are correctly out of scope (see Impact), but the live ones need a
considered rewrite, and one existing architecture test
(`tests/architecture/test_no_personal_strings.py`) needs a scope fix or it will
silently cover less than it does today (see Impact).

## What Changes

- **`BACKLOG.md` and `BACKLOG-CLOSED.md` are deleted.** Success is deletion —
  if either file survives this change, the change failed. The deletion is its
  own commit, separate from migration commits, so reverting it if beads is
  abandoned is one `git revert`.
- **`bd` (v1.1.2+, `github.com/gastownhall/beads`) is adopted in embedded
  mode**, initialized via `bd init --non-interactive --role maintainer`.
  **BREAKING** for anyone's muscle memory around `BACKLOG.md`, and for any
  tooling that greps it.
- **Server mode is explicitly NOT adopted.** Embedded mode serves one writer
  at a time, which matches actual usage (mostly one agent, occasionally
  several in different worktrees, not literally the same instant). Noted as
  the documented upgrade path if genuine concurrent-write conflicts appear.
- **Every open `BACKLOG.md` item becomes a bead**, using the status/dependency
  mapping in `design.md`. Every closed `BACKLOG-CLOSED.md` item becomes a
  closed bead (not deleted — Dolt keeps history, same rationale the file
  header already states for keeping closed entries instead of deleting them).
- **Narrative/evidence content that was never a trackable work item** (the
  "RETIRED (WRONG)" retraction, the "file-size ledger" framing essay, the
  TRACKS dependency-graph writeup) is **not** forced into bead descriptions.
  It moves to `docs/findings/` — the home `CLAUDE.md` already names for
  exactly this ("a backlog entry that needs more than a paragraph of proof
  should carry a pointer, not the proof"). This is the same rule the repo
  already applies to `BACKLOG.md` today, carried into the new medium, not a
  new policy.
- **`.beads/issues.jsonl` is committed to git** (`export.auto: true`,
  `export.git-add: true`), as a plaintext, greppable fallback — see Impact for
  why this matters specifically for this repo's existing comments.
- **`CONSTITUTION.md`'s BACKLOG references are rewritten**, in this repo's
  copy directly, despite its own header ("Canonical source: github.com/
  yoselabs/a2kit... Drift between the two is a bug"). This is an explicit,
  authorized departure from that sync process, not an oversight — recorded in
  `design.md`.
- **`tests/architecture/test_no_personal_strings.py`'s scan scope is
  widened** to cover `.beads/issues.jsonl`, closing a gap this change would
  otherwise open silently (see Impact and the `enforcement-integrity` delta
  below).

## Capabilities

### New Capabilities

- `work-queue`: the repo's deferred/open-work tracking mechanism — what stores
  a deferred item, what its lifecycle states mean, how it links back to the
  OpenSpec change or finding that motivated it, and what must be true before
  the old flat-file queue can be deleted.

### Modified Capabilities

- `enforcement-integrity`: the personal-identifier scan
  (`test_no_personal_strings.py`) SHALL cover every text-ish artifact the
  shipping tree distributes, including the new `.beads/issues.jsonl` export —
  today's suffix allowlist (`_SUFFIXES`) omits `.jsonl`, which would let this
  migration move personal-identifier-bearing prose out of scanned `.md` files
  and into an unscanned export while the guard keeps reading green.

## Impact

**Code and config:**
- `BACKLOG.md`, `BACKLOG-CLOSED.md` — deleted.
- `CONSTITUTION.md:184-186,205,431,457,494-495` — BACKLOG prose rewritten to
  describe the bd-backed queue; Article V's "requesting product's BACKLOG"
  becomes a role a2web fulfills via `bd`, not a file.
- `CLAUDE.md` — the "Backlog" section (currently describing `BACKLOG.md` +
  `BACKLOG-CLOSED.md` lifecycle) rewritten to describe `bd` commands; new
  `.beads`-related scaffolding files (`AGENTS.md`, `.claude/settings.json`)
  land alongside it (verified: `bd init` writes both fresh in this repo, since
  neither exists yet) with one required correction — see `design.md` on the
  `bd remember` conflict.
- `tests/architecture/test_no_personal_strings.py:34,47-49` — `_SUFFIXES` and
  `_SKIP_PREFIXES` updated to scan `.beads/issues.jsonl`; the existing
  denylist (`iorlas`, the operator's egress IP, `/Users/`) applies to it like
  any other tracked text file.
- `tach.toml:42`, `Makefile:22`, `.pre-commit-config.yaml:32`,
  `.github/workflows/release.yml:10` — 4 prose comments citing `BACKLOG.md` by
  searchable phrase rewritten to cite the equivalent `bd-xxxx` issue ID. **This
  is a modest, accepted readability regression**: a phrase is greppable by
  anyone with a text editor; a bead ID needs `bd` installed and the Dolt ref
  fetched to resolve. No mitigation proposed beyond the committed JSONL export
  (which makes the ID at least greppable back to its title/description, even
  without `bd` installed).
- `src/a2web/handler_probe.py:160`, `src/a2web/llm_resource.py:263`,
  `src/a2web/llm_eval/extraction.py:8,238`, `src/a2web/llm_eval/__main__.py:267`,
  `src/a2web/packages/__init__.py:19` — 6 comments, same treatment.
- `tests/capabilities/cascade_decision_log/test_decide_next.py:30-31` — 1
  docstring reference, rewritten.

**Left untouched, on existing repo precedent** (`test_no_personal_strings.py`'s
own docstring: *"Rewriting shipped history to look tidier is the opposite of an
honest engineering log"*):
- `openspec/changes/archive/**` (~90 references across 40+ files)
- `docs/history/A2KIT_FEEDBACK_*.md` (2 references)
- `eval/findings_*.md` (9 references)
- `benchmarks/**` (2 references)
- `README.md`, `CHANGELOG.md` (reviewed case-by-case in `tasks.md`; likely
  narrative, not process instructions)

**New files:**
- `.beads/` (config.yaml, metadata.json, hooks/, issues.jsonl — committed;
  embeddeddolt/ — gitignored)
- `AGENTS.md`, `.claude/settings.json`, `.agents/skills/beads/`,
  `.codex/{config.toml,hooks.json}` — written by `bd init`; verified none of
  these exist in this repo today, so this is a clean addition with one
  required follow-up edit (the `bd remember` conflict, `design.md`).
- `docs/findings/` gains 1 file for BACKLOG.md's retired narrative content
  (exact split enumerated in `tasks.md`).

**No dependency changes to `src/`.** This is a repo-process change; no
runtime code imports `bd`.

## Non-Goals

- **`openspec/changes/*/tasks.md` migration into beads.** Upstream Beads
  guidance suggests seeding beads from `tasks.md` and deleting it; doing that
  here would make the 134 archived changes non-self-contained records. A
  possible future change, not this one.
- **`bd remember` / `bd prime` for persistent memory.** Out of scope — this
  repo does not adopt a fourth memory system on top of the three already in
  use. `bd init`'s auto-generated `CLAUDE.md` block instructs agents
  otherwise; `design.md` specifies the required override.
- **Server mode** (`dolt sql-server`). Noted as the upgrade path, not adopted.
- **Cross-repo / cross-product queue.** This change is scoped to a2web; the
  Constitution edit only removes a2web's own instance of the BACKLOG
  reference, it does not touch the a2kit canonical copy.
- **Any change to the 134 archived changes' contents.**
- **Syncing to GitHub Issues, GitLab, Linear, Jira, or ADO.** Beads v1.0+
  supports this via `bd setup <tracker>`; whether a2web (a public repo) wants
  external-tracker visibility is a separate decision, not a consequence of
  adopting `bd` internally.
