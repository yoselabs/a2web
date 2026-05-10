## Context

PR10 added `LogsRouter` (replay/tail/grep), `log/reader.py`, and `utils/duration.py` on top of the existing PR4 NDJSON writer. The writer + on-disk format are stable and useful; the read surface is the part being removed. Nothing outside the test suite imports the reader, the duration helper, or the new pydantic response models — verified by grep before scoping this change.

## Goals / Non-Goals

**Goals:**
- Reduce v0.1 public surface area to what's actually exercised: `WebRouter.fetch` + the on-disk NDJSON.
- Restore `routers.py` to a single-class module so adding the next router is an obvious additive change.
- Keep the writer, the on-disk format, and every existing log-writer test untouched.

**Non-Goals:**
- Touching the writer, rotation, gzip, log paths, or `LogRecord` shape.
- Designing the eventual replay-from-cache feature (lives in `BACKLOG.md` after the `release-v0-1` change lands).
- Migrating any persisted state — there is none beyond the NDJSON files themselves, which are unaffected.

## Decisions

**Delete, not deprecate.** No real consumers exist. A deprecation period would only carry the API surface into v0.1 release notes for no behavioral benefit.

**Restore `routers.py` as a single-class file.** PR10 inflated it to ~140 LOC with three response models and helpers. Reverting to the WebRouter-only shape (~35 LOC) keeps the module obvious; if a second router lands later, that's the moment to consider splitting into a `routers/` package — not now.

**Keep `utils/__init__.py` empty** rather than deleting `utils/`. The package already hosts `time.py` (used by the orchestrator narrative), so the directory stays.

**Spec delta uses REMOVED, not MODIFIED.** The two PR10 requirements (`Log reader iterates records...`, `LogsRouter exposes replay / tail / grep`) are being deleted wholesale. Per OpenSpec convention REMOVED requires `**Reason**` + `**Migration**` blocks; the migration is "use `tail`/`grep`/`jq` against `~/.a2web/logs/` directly."

## Risks / Trade-offs

- **Risk**: Anyone (including future-me) who already wired `a2web logs replay` into a workflow has it break silently.
  - **Mitigation**: We're pre-v0.1, with no shipped users. The `release-v0-1` change documents the removal in CHANGELOG.md.

- **Risk**: Coverage % could dip if reader code paths were inflating the percentage above some threshold.
  - **Mitigation**: Both code and tests are deleted in lockstep — the deleted lines were almost entirely covered by the deleted tests, so the ratio holds. Verified by running `make test` after the delete.

- **Trade-off**: Losing a useful 80%-ready feature feels wasteful, but it's recoverable from git history when the proper replay-from-cache lands. The cost of shipping it now is documenting a tool surface we're going to break later anyway.

## Migration Plan

There's no user-facing migration. Operators who used `a2web logs replay --url=…` should use `grep` / `jq` over the NDJSON files directly:

```sh
jq 'select(.url=="https://nyt.com/article")' ~/.a2web/logs/fetches-*.ndjson | tail -n 1
```

The companion `release-v0-1` change adds a `BACKLOG.md` entry "PR10b — replay-from-cache" so the deferred work is tracked.

Rollback is a `git revert` of the removal commit.
