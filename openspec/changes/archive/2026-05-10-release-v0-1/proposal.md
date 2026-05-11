## Why

We've shipped 10 numbered PRs (PR1–PR8 + PR10) plus their archives, the cascade is feature-complete for the v0.1 contract, and the only pre-tag cleanup left is the `remove-logs-router` companion change. After that lands the repo is at an honest v0.1 state — but the version string still says `0.1.0.dev0`, there's no `CHANGELOG.md`, and the deferred work (PR7e proxy polish, PR8b youtube/substack/twitter, PR10b replay-from-cache, the explicit v0.2/v0.3 items in engineering.md §10) lives only in scattered CLAUDE.md sentences and archived `proposal.md` "Out of Scope" sections. Cutting v0.1.0 properly means: bump the version, write the changelog summarizing what shipped, consolidate every deferred item into a single `BACKLOG.md`, and tag the commit. This change packages those four steps so the release is reproducible and the post-v0.1 plan is visible in one place.

## What Changes

- Bump `pyproject.toml` `version` from `0.1.0.dev0` to `0.1.0`. Confirm classifiers still say `Development Status :: 3 - Alpha` (3 = Alpha is appropriate for a v0.1 first cut; promote to Beta later).
- Create `CHANGELOG.md` at repo root following Keep-a-Changelog style. The first entry is `## [0.1.0] - 2026-05-10` with `### Added` / `### Changed` / `### Removed` sections summarizing PR1–PR10 (the `Removed` section will reference the `remove-logs-router` change once it lands; we sequence: remove-logs-router merges first, then this change). Include a header note: "This is the first tagged release; entries summarize the full PR1–PR10 build."
- Create `BACKLOG.md` at repo root. Single grouped list of every deferred item we know about, each with: source PR / engineering doc reference, one-line description, why it was deferred, and rough scope tier (S/M/L). Groups: **Proxy polish (PR7e)**, **Site handlers (PR8b)**, **Replay (PR10b)**, **v0.2 candidates** (Reader-LM v2 fallback, multimodal fetch, browser-as-a-service remote CDP), **v0.3+** (VLM image captioning, distributed cache, webhook callbacks). Mirror the table I sketched in chat: PR7e items × ~6, PR8b × 3, PR10b × 3, v0.2 × 3, v0.3+ × 4.
- Update `README.md` if it carries `dev0` / "in development" caveats — replace with v0.1 install + quickstart + a "see BACKLOG.md for what's next" pointer. Keep edits minimal; this change is not a README rewrite.
- After `make check` passes on the bumped tree, commit and tag `v0.1.0` (annotated tag, message `a2web v0.1.0 — cascade feature-complete`). Push of the tag is left to the operator (per the `feedback_no_prs` memory: solo repo, manual git ops).

This change runs **after** `remove-logs-router` archives. Sequencing matters: the changelog's "Removed" section references that change; bumping the version with the LogsRouter still in the tree would mean shipping then immediately retracting an MCP tool.

## Capabilities

### New Capabilities

(none — release plumbing only; no behavioral capabilities introduced)

### Modified Capabilities

(none — no spec requirement changes; this change touches version metadata, CHANGELOG, BACKLOG, and README only)

## Impact

- `pyproject.toml`: 1-line version bump
- `CHANGELOG.md`: new file at repo root, ~80–120 lines
- `BACKLOG.md`: new file at repo root, ~60–100 lines (table or grouped lists)
- `README.md`: small edits (or none if it's already version-agnostic)
- Git: one commit + one annotated tag (`v0.1.0`); no push
- No code changes, no test changes (existing test suite continues to gate the release)
- No spec deltas (`openspec/specs/` untouched)
- Public surface: unchanged from `remove-logs-router` end-state
- Rollback: delete the tag, revert the commit. No persisted state, no shipped artifacts beyond the local tag.
