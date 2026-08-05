## Context

`BACKLOG.md` + `BACKLOG-CLOSED.md` are read by every agent session that asks
"what's deferred / what's next". They are not uniform: sampling the headings
shows at least four shapes under one `## ` level — a single trackable issue
(*"the comment-thread handlers extract links they cannot carry (S,
structure)"*), a dependency-graph writeup (*"TRACKS: how the 2026-07-31
findings group, and what depends on what"*), a plan-over-issues (*"THE CHANGE
SET: which tracks became OpenSpec proposals"*), and a pure retrospective with
no lifecycle (*"RETIRED (WRONG) — 'a losing tier's structured output is
discarded'"*). Several `## ` headings (`VERIFIED — structural defects`,
`HYPOTHESES — probe before believing`) contain multiple `### ` sub-items, each
independently trackable. **The 71-heading count is not a work-item count.**

Beads is a graph issue tracker (`github.com/gastownhall/beads`, v1.1.2
verified installed via `brew install beads`, formerly `steveyegge/beads` —
the repo transferred orgs, per that release's own changelog: *"fix: update
goreleaser owner to gastownhall (repo moved from steveyegge)"*). It models one
of these four shapes well — the single trackable issue — and has no shape for
the other three. This design's central move is not "migrate 71 headings to 71
beads"; it's **classify each block by shape, and give each shape its correct
home**, only one of which is beads.

## Goals / Non-Goals

**Goals:**
- Every currently-open, currently-trackable `BACKLOG.md` item becomes a real
  bead with correct status, priority, and dependency edges.
- Every closed `BACKLOG-CLOSED.md` item becomes a closed bead — history
  preserved, not deleted, matching the file's own stated reason for existing.
- Narrative/evidence content that isn't a work item gets a home in
  `docs/findings/`, not force-fit into a bead description.
- The bead ↔ OpenSpec-change linkage is a real field (`--spec-id`), not a
  free-text convention that can drift.
- The personal-identifier scan keeps its actual coverage after the migration,
  not just its passing status.
- The change is revertible in one commit if beads is abandoned.

**Non-Goals:**
- Migrating `openspec/changes/*/tasks.md` into beads (stated in proposal.md).
- Adopting `bd remember`/`bd prime` for persistent memory.
- Server mode, cross-repo queue, external-tracker sync (GitHub Issues/GitLab/
  Linear/Jira/ADO — all real `bd setup` targets in v1.0+, deliberately not
  exercised here).
- Perfectly preserving `BACKLOG.md`'s prose voice in bead titles/descriptions
  — beads titles are meant to be skimmed one-per-line in `bd ready`/`bd list`;
  some compression from the original heading's clause-heavy style is expected
  and fine.

## Decisions

### D1 — Status mapping: three distinct "not ready" states, not one

Verified via `bd statuses` on the real v1.1.2 install and confirmed
empirically (create issue A, add a `blocks` dependency from B onto A, inspect
`bd show B --json` and `bd ready`/`bd blocked`):

| BACKLOG.md pattern | bd mechanism | why |
|---|---|---|
| "waiting on [tracked issue X]" | real `blocks` dependency | auto-clears when the blocking bead closes — verified: a dependency-blocked issue's stored `status` stays `open`, it is excluded from `bd ready`, and surfaced via `bd blocked` — it is a derived flag (`is_blocked`), not a manual status write |
| "REVISIT, do not act yet" / shelved with nothing specific blocking it | `bd defer <id> --reason "..."` | native status; docs: *"Deliberately set aside — not blocked by anything specific, just postponed... Unlike blocked issues, there's no dependency keeping them from being worked."* Matches the twitter-handler "REVISIT" entry and similar exactly |
| "waiting on X" where X has no bead of its own (external API access, a human decision) | manual `bd update <id> --status blocked` | the one case dependency modeling can't express, because there's no second issue to point at |

`bd defer --reason` appends the reason to the issue's notes field
automatically (verified) — the handover's open question "how do we record why
something is deferred" is answered by the tool, not a repo convention.

Rejected: modeling every "on hold" entry as a synthetic blocking dependency
(the original handover's assumption, written before `bd statuses` was
checked). It would create a bead purely to be a blocker, misrepresenting
"nothing specific is blocking this, we just haven't gotten to it" as "blocked
by a named thing".

### D2 — Bead ↔ OpenSpec-change linkage: `--spec-id`, not free text

Verified: `bd update <id> --spec-id "openspec/changes/<name>/proposal.md"`
round-trips as a `spec_id` field in `bd show --json`. This is a real, typed
field ("Link to specification document" per `bd update --help`), not a
substring in the description that could drift or typo silently. Every bead
whose BACKLOG.md entry named the change that would resolve it (e.g. "Surfaced
by `repay-the-shelf-debt` §3.4") gets `--spec-id` set at migration time.

### D3 — Branch/commit provenance: `--set-metadata`, documented as a repo convention

No dedicated field exists for "which branch/commit did this land on" — beads
has `--external-ref` (shaped for `gh-9`/`jira-ABC` cross-tracker IDs, not git
refs) and free-form `--set-metadata key=value`. Verified:
`--set-metadata branch=<name> --set-metadata commit=<sha>` round-trips as a
`metadata` object in `bd show --json`. This is not enforced by the tool —
it's a convention this change documents (in the rewritten `CLAUDE.md`
section) using exactly the keys `branch` and `commit`, so a future session
doesn't invent `git_branch`/`sha`/`ref` variants that don't agree with each
other.

### D4 — Committed `.beads/issues.jsonl`, with the staleness gap closed

Committing the JSONL export was weighed against leaving it gitignored
(cleaner diffs, fully trusts `bd` as the interface). Decided **yes, commit
it** — because this repo specifically has ~12 in-code comments
(`tach.toml:42`, `Makefile:22`, etc.) that cite backlog items by searchable
phrase today. After migration those same comments cite a `bd-xxxx` hash ID.
Without a committed, plaintext export, resolving that ID requires `bd`
installed and the Dolt ref fetched — a real regression for anyone browsing
the repo cold (a new contributor, a code-search tool, a future audit). A
committed JSONL means `grep -r bd-a1b2 .beads/issues.jsonl` still resolves
the title and description without any tooling.

**The gap the docs implied turned out not to exist, verified empirically
against the real v1.1.2 install in this repo (not re-derived from docs a
second time):** the concern was that `export.auto` only re-exports
piggybacked on a **code** commit via the `pre-commit` hook, leaving the JSONL
stale across a queue-only session. Tested directly: `bd create` (no source
change, no commit at all) caused `.beads/issues.jsonl` to appear and get
staged (`export.git-add`) immediately, synchronously, as part of the `create`
call itself — not deferred to any git hook. `export.auto`/`export.git-add`
fire on every mutating command, so the file is never stale between writes
regardless of whether or when a commit happens. **No pre-push hook chaining
was added** — it would be a no-op given this behavior, and adding one purely
for symmetry with the original (incorrect) assumption would be exactly the
kind of unverified mechanism this repo's conventions warn against. If a
future `bd` version changes this to a batched/hook-triggered export, re-open
this decision then, verified the same way (empirically, not by re-reading
docs).

### D5 — CONSTITUTION.md edited directly, with the sync-process deviation stated

`CONSTITUTION.md`'s header states: *"Canonical source:
github.com/yoselabs/a2kit/blob/main/CONSTITUTION.md. This is a verbatim copy
synced manually. To propose changes, edit the a2kit copy first."* This change
edits the a2web copy directly instead, per explicit user authorization. The
stated reason: `~/Workspaces/a2kit`'s own most recent commit (2026-07-15,
not archived on GitHub but not being actively maintained as a Constitution
source either) is titled *"reframe refound — surviving substrate's home is
the shelf, a2kay pilots"* — a2kit's own App/DI-substrate role, the thing
Article V's BACKLOG-purity rule was written to protect, is itself being
retired and refounded elsewhere. Treating a2web's copy as the practical
authority for its own product-level BACKLOG reference is reasonable in that
context.

**This is recorded as a known, authorized departure, not silently absorbed.**
`tasks.md` includes a task to add a dated note near the file's existing sync
header acknowledging the drift, so a future reconciliation (if a2kit's
Constitution role is ever reactivated) has something to diff against rather
than discovering silent divergence.

Article V's actual wording (*"Refusal is recorded in the requesting product's
BACKLOG... never in the substrate's BACKLOG"*) needs no semantic change —
"BACKLOG" there names a role (where a product records a refused substrate
feature), which a2web now fulfills via `bd` instead of a file. The
Enforcement Inventory's `REGO-SUBSTRATE-BACKLOG-PURITY` row
(`CONSTITUTION.md:431`) and the "See also" pointer (`:494-495`) are the two
spots that concretely say "BACKLOG.md" and need the file reference removed.

### D6 — `bd init` mode: `--non-interactive --role maintainer`, not `--team`

Verified: `bd init --team` requires interactive prompts and rejects
`--non-interactive` outright (*"--team requires interactive prompts and
cannot be used with --non-interactive"*). Since this change (and future
`bd init --init-if-missing` reruns, e.g. from a fresh clone) needs to run
non-interactively — from an agent session, from CI, from a scripted setup —
`--role maintainer` is the equivalent non-interactive path. `--contributor`
was considered and rejected: it's for hiding a private tracker inside a fork
of someone else's repo (*"best for open source contributors... private task
tracking on public repos"*); a2web is the maintainer's own repo, and Team's
shared-in-repo model (which `--role maintainer` produces without the wizard)
is the actual fit.

### D7 — The auto-generated `CLAUDE.md` block conflicts with an existing decision

Verified empirically (scratch clone, pre-populated `CLAUDE.md`): `bd init`
appends a versioned, marker-delimited block
(`<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:... -->` ...
`<!-- END BEADS INTEGRATION -->`) without touching existing content — safe by
design. But the injected text includes: *"Use `bd remember` for persistent
knowledge — do NOT use MEMORY.md files."* This repo does not adopt `bd
remember` (Non-Goals). Editing the text inside the markers directly risks a
future `bd doctor`/`bd prime` divergence check flagging the file as drifted
from the version it thinks it installed (the tool tracks a `hash:` in the
marker specifically to detect this). Instead, `tasks.md` adds one line of
override prose in `CLAUDE.md` **outside and below** the marker block, stating
plainly that `bd remember`/`bd prime` are not adopted here — memory stays
with the existing (unrelated, user-level) memory system. This preserves the
tool's ability to manage its own block while keeping the repo's actual policy
visible and correct.

## Risks / Trade-offs

- **[Risk] The personal-string scan silently narrows.** `.jsonl` is not in
  `test_no_personal_strings.py`'s `_SUFFIXES` allowlist
  (`tests/architecture/test_no_personal_strings.py:34`), and
  `.beads/embeddeddolt/` is gitignored/binary. Migrating 3648 lines of prose
  — including the operator IP address the same test already denylists at
  line 38 — out of scanned `.md` files and into an unscanned `.jsonl` would
  make the guard read as covering the same ground while covering less.
  **Mitigation:** this change adds `.jsonl` to `_SUFFIXES` as part of the
  `enforcement-integrity` spec delta (see `specs/`), verified red-then-green
  per this repo's own convention for guard changes (`close-guards-that-read-
  green`'s stated method: widen before fixing, so the red run is the
  evidence the widened matcher works).
- **[Risk] `bd-xxxx` IDs are opaque without tooling.** ~12 in-code comments
  that cite `BACKLOG.md` by phrase today will cite a hash ID. **Mitigation:**
  committed `.jsonl` (D4) makes the ID at least greppable to its title/body
  without `bd` installed; this does not fully restore today's zero-tooling
  readability, and the proposal states that cost rather than hiding it.
- **[Risk] Migration undercounts or overcounts work items.** A raw heading
  count (71 → 71 beads) is a false oracle — see Context. **Mitigation:**
  verification is content-addressed: every `##`/`###` block's substantive
  content must be traceable to either a bead (queue items, checked via `bd
  list --spec-id` back-reference where applicable) or a `docs/findings/`
  file (narrative), enumerated explicitly in `tasks.md`, checked before the
  deletion commit.
- **[Risk] Abandoning beads later is expensive.** **Mitigation:** the
  deletion of `BACKLOG.md`/`BACKLOG-CLOSED.md` is its own commit, separate
  from migration commits (`tasks.md` sequencing) — `git revert
  <deletion-commit>` restores the files verbatim if beads is abandoned within
  the commit's lifetime. `.beads/issues.jsonl` being committed means the
  queue's content also survives in the git history independent of the Dolt
  DB, which is the actual durable rollback story: even a corrupted or lost
  `.beads/embeddeddolt/` leaves the last-exported JSONL recoverable from git.
- **[Trade-off] Embedded mode is single-writer.** Accepted — matches actual
  usage (D6 context). If genuine concurrent-write conflicts appear (literal
  same-instant writes from two agents in two worktrees), server mode
  (`dolt sql-server`) is the documented upgrade path, not a repo-invented
  workaround.

## Migration Plan

1. Install `bd` (already verified working, v1.1.2).
2. `bd init --non-interactive --role maintainer` in the working repo — first
   time this touches the real repo, after everything above was verified in
   scratch clones only.
3. Enable `export.auto`/`export.git-add`; add the `pre-push` export chain
   (D4).
4. Classify every `BACKLOG.md`/`BACKLOG-CLOSED.md` block by shape (Context);
   enumerate the classification in `tasks.md`.
5. Create beads for every trackable item (open → matching status per D1,
   closed → `closed` status), with dependencies (D1), `--spec-id` (D2), and
   `--set-metadata branch=/commit=` where the original entry named one (D3).
6. Move narrative/evidence-only content to `docs/findings/`.
7. Rewrite live process docs (`CLAUDE.md`, `CONSTITUTION.md`, `README.md`)
   and in-code comments (Impact list in `proposal.md`) to cite `bd`/bead IDs.
8. Widen `test_no_personal_strings.py` coverage; verify red-then-green.
9. Verify: every original block accounted for (content-addressed, not
   counted) — checklist in `tasks.md`.
10. Commit the deletion of `BACKLOG.md`/`BACKLOG-CLOSED.md` **separately**
    from every commit above.

**Rollback:** `git revert` the deletion commit restores the files verbatim.
The bead data (and its JSONL export) can be left in place harmlessly — a
reverted `BACKLOG.md` and a populated `.beads/` are not mutually exclusive,
they'd just be redundant until a human decides which one to trust going
forward.

## Open Questions

- Whether to also configure `bd setup github` (issue-sync to GitHub Issues)
  given a2web is a public repo — explicitly deferred (Non-Goals), but likely
  the first follow-up someone asks about after this ships.
- Whether `docs/findings/` needs its own index/README once it absorbs
  BACKLOG.md's narrative content, or whether the existing convention
  (file-per-finding, referenced by date) scales without one — not blocking
  this change, worth a note in `tasks.md` if the resulting file count is
  large.
