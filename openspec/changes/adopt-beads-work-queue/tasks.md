# Tasks

Every fact below citing a line number, a doc claim, or a `bd` behavior was
verified against a real v1.1.2 install in a throwaway scratch clone, or against
the current `main` of `github.com/gastownhall/beads`, on 2026-08-05 — re-verify
before implementing if this change sits for long, per this repo's own
"a task's cited evidence is verified at the citation before it is acted on"
convention (`enforcement-integrity` spec).

Do not run `bd init` in the working repo until task 2.1 — everything before it
is scratch-clone or read-only verification.

## 1. Pre-flight (re-verify, don't re-trust)

- [ ] 1.1 Re-run `grep -rIo 'BACKLOG[A-Z-]*\.md' --exclude-dir=.git .` and diff
      against the 165-reference/~20-file baseline in `proposal.md`'s Impact
      section. If the count or file set moved, re-classify the delta before
      proceeding.
- [ ] 1.2 Re-count `BACKLOG.md`/`BACKLOG-CLOSED.md` headings
      (`grep -c '^## ' BACKLOG.md BACKLOG-CLOSED.md`) against 71/20. Recent
      commits land new entries regularly — this is a queue, it moves.
- [ ] 1.3 Confirm `bd` version installed matches or exceeds v1.1.2
      (`bd version`); re-check `bd statuses` and `bd dep add --help` output
      against the status/dependency-type tables in `design.md` D1/`proposal.md`
      if a newer version is available — both lists were verified against a
      specific version and could have changed.
- [ ] 1.4 Confirm `~/Workspaces/a2kit`'s HEAD still supports the "a2kit's
      Constitution role is in flux" reasoning behind D5 — if a2kit has since
      published its own Article V rewrite, reconcile with that instead of
      diverging further.

## 2. Initialize `bd` in the working repo

- [ ] 2.1 `bd init --non-interactive --role maintainer` (D6). Verify the
      commit it produces touches only new files plus an additive
      marker-delimited block in `CLAUDE.md` — no other existing file should
      appear in that commit's diff.
- [ ] 2.2 `bd config set export.auto true`; `bd config set export.git-add true`.
- [ ] 2.3 Add an explicit `bd export` call to the installed `pre-push` hook
      (D4) — this repo's `.beads/hooks/pre-push` is a chained shim; add the
      export step as a chain entry, don't hand-edit the shim body.
- [ ] 2.4 Verify: make a queue-only change (e.g. `bd comment` on a throwaway
      test bead), run the push path without touching source, confirm
      `.beads/issues.jsonl` refreshed. Delete the throwaway bead afterward.

## 3. Classify every BACKLOG.md / BACKLOG-CLOSED.md block

- [ ] 3.1 Walk every `## ` (and, where a `## ` contains `### ` sub-items, every
      `### `) block in both files. Tag each as one of: **issue** (has or
      implies a status/completion criterion), **narrative** (retrospective,
      retraction, measurement writeup — no lifecycle), **plan-over-issues**
      (groups/sequences other entries, e.g. "TRACKS", "THE CHANGE SET").
- [ ] 3.2 Record the classification as a checklist (block heading →
      issue/narrative/plan) — this is the artifact task 6 verifies against,
      not a raw count.
- [ ] 3.3 For each **issue**-tagged block, note: title, priority tier (S/M/L →
      bd priority per the table in `docs/core-concepts/issues.md`), any
      "waiting on X" language (→ D1's three-way split), any named OpenSpec
      change (→ `--spec-id`), any named branch/commit (→ `--set-metadata`).

## 4. Migrate issues

- [ ] 4.1 Create a bead per **issue**-tagged open block from `BACKLOG.md`,
      using the mapping from 3.3 and the status rules in D1.
- [ ] 4.2 Create a bead per **issue**-tagged block from `BACKLOG-CLOSED.md`,
      immediately closed (`bd close <id> --reason "..."`), preserving whatever
      closing rationale the original entry gave.
- [ ] 4.3 Wire dependencies: for every "blocked on X" reference between two
      migrated beads, add the real `blocks` edge (D1). For "supersedes"
      language, use `--type supersedes` rather than deleting the superseded
      entry.
- [ ] 4.4 For blocks naming an OpenSpec change as source or resolver, set
      `--spec-id` (D2).
- [ ] 4.5 Move **narrative**-tagged and **plan-over-issues**-tagged blocks into
      `docs/findings/` — one file per coherent group is fine; don't force a
      1:1 file-per-heading split if several blocks are one continuous argument
      (e.g. the "TRACKS" + "THE CHANGE SET" pair).
- [ ] 4.6 For any migrated bead whose justification is longer than a short
      paragraph, add a comment/note pointing at the corresponding
      `docs/findings/` file rather than pasting the full text into the bead
      description.

## 5. Rewrite live process docs and code comments

- [ ] 5.1 `CLAUDE.md` — rewrite the "Backlog" section to describe `bd`
      commands and the D1/D2/D3 conventions (status mapping, `--spec-id`,
      `--set-metadata branch=/commit=`).
- [ ] 5.2 `CLAUDE.md` — add the D7 override line stating `bd remember`/
      `bd prime` are not adopted for memory, placed outside and below the
      `bd init`-managed marker block.
- [ ] 5.3 `CONSTITUTION.md` — rewrite `:184-186,205` (Article V prose),
      `:431` (Enforcement Inventory row), `:494-495` (See also) per D5. Add
      the dated authorized-deviation note near the file's existing sync
      header.
- [ ] 5.4 `README.md` — check for BACKLOG references and update if they
      describe current process (not historical).
- [ ] 5.5 `tach.toml:42`, `Makefile:22`, `.pre-commit-config.yaml:32`,
      `.github/workflows/release.yml:10` — rewrite each to cite the
      equivalent bead ID.
- [ ] 5.6 `src/a2web/handler_probe.py:160`, `src/a2web/llm_resource.py:263`,
      `src/a2web/llm_eval/extraction.py:8,238`,
      `src/a2web/llm_eval/__main__.py:267`,
      `src/a2web/packages/__init__.py:19` — same treatment.
- [ ] 5.7 `tests/capabilities/cascade_decision_log/test_decide_next.py:30-31`
      — rewrite the docstring reference.
- [ ] 5.8 Leave `openspec/changes/archive/**`, `docs/history/`,
      `eval/findings_*.md`, `benchmarks/**` untouched, per proposal.md Impact.

## 6. Close the enforcement gap

- [ ] 6.1 Add `.jsonl` to `test_no_personal_strings.py`'s `_SUFFIXES`
      (currently `tests/architecture/test_no_personal_strings.py:34`).
- [ ] 6.2 Run the widened scan against the repo **before** any content is
      touched — confirm it's still green at this point (nothing in
      `.beads/issues.jsonl` yet, since `bd init` was just run). This is the
      "verify red-before-green" step in spirit: prove the widened suffix
      actually gets scanned by temporarily seeding a denylisted string into a
      throwaway bead, exporting, confirming the test fails, then removing the
      throwaway bead and re-exporting.
- [ ] 6.3 After the real migration (section 4) is complete, run the full guard
      again and fix any genuine denylist hit surfaced from migrated bead text.

## 7. Verify migration completeness (content-addressed, not counted)

- [ ] 7.1 For every block tagged in 3.2, confirm it resolves to exactly one
      of: a bead (`bd list --spec-id <path>` or manual lookup), a
      `docs/findings/` file, or an explicit "deliberately dropped, reason: X"
      note (only if a block is judged genuinely obsolete — should be rare).
- [ ] 7.2 Spot-check 5 migrated beads against their original `BACKLOG.md` text
      for lossy compression — titles are expected to compress, but no
      substantive detail (a cited `file:line`, a measurement, a rejection
      reason) should be silently dropped.
- [ ] 7.3 Confirm `bd ready`/`bd blocked`/`bd list --status deferred` produce
      a sensible, non-empty picture matching what a human skimming the old
      `BACKLOG.md` would expect to see as "next".

## 8. Delete, as its own commit

- [ ] 8.1 Commit everything above (init, migration, doc rewrites, guard
      widening).
- [ ] 8.2 In a **separate** commit, `git rm BACKLOG.md BACKLOG-CLOSED.md`.
- [ ] 8.3 Run `make check` after the deletion commit — confirm the widened
      personal-string scan and all other guards stay green with the files
      gone.
