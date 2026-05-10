## Context

Ten archived OpenSpec changes (PR1–PR8 + PR10) since the project started, plus the in-flight `remove-logs-router`. Version pinned at `0.1.0.dev0` since PR1. No CHANGELOG, no BACKLOG, README is the original placeholder. Engineering.md §10 lists explicit v0.2/v0.3 deferrals; PR7c/PR7d/PR8/PR10 each deferred items in their proposals' "Out of Scope" sections; CLAUDE.md mentions PR7e and PR10b in passing — but no consolidated post-v0.1 view exists.

This is release plumbing, not feature work. The design questions are about where things live and what counts as "v0.1.0".

## Goals / Non-Goals

**Goals:**
- Ship a real `0.1.0` (not `dev0`) with a tag that future work can branch from.
- Capture every deferred item we know about in one place so post-v0.1 planning isn't archaeology.
- Keep CHANGELOG honest and short — readers shouldn't need to crawl PR archives to know what's in v0.1.
- Sequence cleanly behind `remove-logs-router` so the release doesn't ship a tool we immediately retract.

**Non-Goals:**
- Rewriting the README (separate work; the existing one is functional even if minimal).
- Designing the deferred items themselves — `BACKLOG.md` describes them, doesn't solve them.
- Promoting classifier from Alpha → Beta. v0.1 is honestly Alpha; promotion follows real-world usage.
- Publishing to PyPI. Tag-only for now; PyPI is a separate decision.

## Decisions

**One change, not three.** Version bump + CHANGELOG + BACKLOG could each be a tiny change. Bundling them is correct because they only make sense together: a version bump without a changelog is opaque, a CHANGELOG without a backlog leaves readers asking "what's next." All three artifacts are repo-root metadata files, none carry spec implications, none change behavior.

**Sequence after `remove-logs-router`.** Listed alternatives: (a) include the removal in this change, (b) tag v0.1.0 with LogsRouter still in tree and remove later. (a) blurs concerns and makes the spec delta in `remove-logs-router` redundant. (b) ships an MCP tool surface we plan to delete — bad faith with anyone who looks at v0.1.0 release notes. The two-change sequence is cleanest.

**`BACKLOG.md` at repo root, not in `openspec/`.** OpenSpec is for in-flight specs and changes; consolidated future work is closer to a roadmap. Repo-root visibility matches CHANGELOG and README. An optional pointer line in CLAUDE.md ("see BACKLOG.md for deferred work") makes it discoverable from the docs every Claude session reads.

**CHANGELOG groups by Keep-a-Changelog headers, not by PR.** Readers care about user-facing changes, not internal PR boundaries. Internal PR references go in parentheses for traceability. Example: `Camoufox-based browser tier with lazy pool and graceful import-fail (PR7c)` under `### Added`.

**Annotated git tag, not lightweight.** Annotated tags carry author, date, and message — required for any future "what was in v0.1" forensics. Pushing the tag is the operator's choice (per `feedback_no_prs`: solo repo, manual git ops); the change creates the tag locally only.

**`make check` is the release gate.** No new CI step. If lint/ty/test pass on the bumped tree, the commit ships. Coverage threshold (≥85%) is the existing line.

## Risks / Trade-offs

- **Risk**: Tagging `v0.1.0` locks the contract. If we forgot something, the next release becomes `0.1.1` rather than retroactive edits.
  - **Mitigation**: Tag is local until pushed. The two-change sequence (remove-logs-router → release-v0-1) gives a final review window before tagging.

- **Risk**: BACKLOG drifts immediately — items get done, scope shifts, new deferrals appear. A stale backlog is worse than none.
  - **Mitigation**: Treat BACKLOG.md as living: each new openspec change that defers something updates it; each PR that ships a backlog item removes the entry. CLAUDE.md can carry the "keep BACKLOG fresh" reminder under a maintenance bullet.

- **Trade-off**: `0.1.0` carries `Development Status :: 3 - Alpha` rather than Beta. Some users equate `0.1.0` with "stable enough to use." We're calling it Alpha honestly because the cascade has not been exercised against a wide enough URL distribution. The classifier is the truthful signal.

## Migration Plan

This is a release, not a migration. Sequence:

1. `remove-logs-router` archives (separate change, prerequisite).
2. Open this change. Bump `pyproject.toml`. Write `CHANGELOG.md` and `BACKLOG.md`. Edit `README.md` minimally if needed.
3. Run `make check`. If green, commit "Release v0.1.0".
4. Annotate tag: `git tag -a v0.1.0 -m "a2web v0.1.0 — cascade feature-complete"`.
5. Operator decides whether to push the tag.

Rollback: `git tag -d v0.1.0` and `git revert <commit>`. No published artifacts to retract (no PyPI publish in this change).

## Open Questions

- README rewrite: in-scope (light touch only) or follow-up? Going with light touch; full rewrite later when we have install/usage signal from real users.
- PyPI publish: out of scope. Decision tied to whether v0.1 is "share with people" or "tag for self." Default to local-only; publish later.
- BACKLOG format: grouped Markdown list vs. table. Grouped list reads better when entries have multi-line "why deferred." Table reads better at scale. Going with grouped list for v0.1; table-ify if BACKLOG passes ~30 entries.
