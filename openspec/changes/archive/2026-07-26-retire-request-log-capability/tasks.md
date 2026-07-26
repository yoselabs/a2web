# Tasks

The witness is `git show 9140fc5` (the nuke commit) + the absence of
`src/a2web/log/record.py`, `writer.py`, `paths.py`, and any `LogWriter` /
`log_writer` symbol in `src/a2web/`. Spec-only change; no code to write.

## 1. Retire the capability
- [x] 1.1 Author `specs/request-log/spec.md` REMOVING all six requirements
      (`LogRecord schema`, `NDJSON writer with lazy open`, `Size-based rotation
      with gzip on rollover`, `Log path resolution`, `Best-effort writes`,
      `Opt-out via settings`), each with a Reason (deleted by `9140fc5`) and a
      Migration pointer (`app-logging` for the surviving `log_enabled`).
- [x] 1.2 `openspec validate retire-request-log-capability` → valid.

## 2. Close (needs archive)
- [x] 2.1 MECHANISM: `openspec archive` refuses to rebuild a zero-requirement
      spec ("Spec must have at least one requirement") — the tool has no
      full-capability-deletion path. So the retirement is done by deleting the
      spec file directly (`openspec/specs/request-log/spec.md`), and the change
      record is archived with `--skip-specs` (the flag intended for changes
      whose spec effect the tool cannot auto-apply). The REMOVED delta documents
      intent; the file deletion is its effect.
- [x] 2.2 Delete `openspec/specs/request-log/spec.md` (capability fully retired).
- [ ] 2.3 Confirm `test_no_a2kit_in_specs.py` is green (request-log no longer
      scanned) and the spec-count floor still clears (41 ≥ 30).

## 3. Cruft note (not this change's scope)
- [ ] 3.1 FOLLOW-UP: `src/a2web/packages/ndjson_log/` is a stale empty dir (only
      `__pycache__`) left by the `9140fc5` nuke + the later package-flatten, and
      `fetcher.py:707` carries an a2kit-branding comment. Both are source
      cleanup, not spec reconciliation — captured for a domain-drift pass.
