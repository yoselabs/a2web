# Tasks

Every guard below must be **verified red before green** against an injected
violation, and the injection recorded in the task notes. This is not ceremony:
the whole change exists because three guards were trusted without anyone
watching them fail.

## 1. Boundary-coverage guard

- [x] 1.1 Remove the retired `ndjson_log` module entry from `tach.toml`, and
      confirm `uv run tach check` no longer prints the `[WARN] … not found in
      project` line it has printed on every run since the package was retired.
- [x] 1.2 Add `tests/architecture/test_tach_covers_every_package.py`: parse
      `tach.toml`, enumerate packages under `src/a2web/packages/` (modules and
      folder-packages both; skip dunder and `README.md`), and assert the two
      sets are equal in both directions.
- [x] 1.3 Give it a non-vacuity floor on BOTH sides — a minimum package count
      and a minimum configured-module count — so a moved directory or an
      unparseable config fails loudly rather than comparing two empty sets.
- [x] 1.4 State the known limit in the docstring: this answers "does a contract
      exist", not "is it tight". A permissive entry passes.
- [x] 1.5 Verify red: temporarily add a package directory with no `tach.toml`
      entry → must fail naming it; temporarily add a config entry for a
      nonexistent module → must fail naming it. Restore.

## 2. Local-shelf-source guard

- [x] 2.1 Add `tests/architecture/test_no_local_shelf_source.py`: parse
      `pyproject.toml`'s dependency source table and assert no entry carries
      `path =` or `editable = true`.
- [x] 2.2 Assert non-vacuously that the source table was found and contains at
      least a floor number of pinned entries (13 today), so a renamed table
      section fails instead of finding nothing to object to.
- [x] 2.3 Docstring must state WHY this duplicates the shelf's git hook: the
      hook resolves its check out of a shelf clone and `exit 0`s when absent,
      so CI and fresh clones have no protection. This check runs in `make
      check`, which CI runs.
- [x] 2.4 Verify red: temporarily repoint one shelf dependency at a local path
      → must fail naming the dependency. Restore.

## 3. Map-citation guard

- [x] 3.1 Choose the historical-mention marker against how `CLAUDE.md` actually
      reads today (design D3 deliberately left the form open). The file's
      existing historical mentions — `packages/http_cache.py`,
      `packages/llm_cost_guard.py`, the promoted `providers/` and
      `cookie_store/` — are the test set the convention must accommodate
      without contorting the sentences.
- [x] 3.2 Add `tests/architecture/test_claude_md_citations_resolve.py`:
      extract repo-relative path citations from `CLAUDE.md`, skip ones carrying
      the historical marker, assert the rest resolve.
- [x] 3.3 Handle the shorthand form already in use — `wobble/_policies.py`,
      `actions/playbook.py` are written relative to `src/a2web/`. Resolve
      against the documented roots rather than flagging them; a guard that
      demands every path be fully-qualified would rewrite the file's voice.
- [x] 3.4 Non-vacuity floor on the number of citations extracted.
- [x] 3.5 Verify red: cite a nonexistent path → must fail; mark a live path as
      historical → must NOT be silently accepted if it still exists (or, if
      that check proves noisy, state in the docstring why it was omitted).

## 4. Correct the four stale citations in `CLAUDE.md`

- [x] 4.1 `src/a2web/_plugin.py` → the shelf `plugin_surface` package
      (`from plugin_surface import PluginManifest, Unavailable`), with
      `_manifests/` unchanged. Verify against an actual manifest module.
- [x] 4.2 `tests/test_packages_independence.py` → `tach.toml` is the enforcer.
      Note in the same sentence that coverage is now guarded (task 1), since
      that is exactly the gap this citation hid.
- [x] 4.3 `tools/hooks/install.py` → it lives in the shelf, not this repo, and
      the hook is best-effort. Per spec, do not describe it as a hard block;
      name the gate check from task 2 as the enforcing mechanism.
- [x] 4.4 Remove `ndjson_log/` from the list of current packages.
- [x] 4.5 Re-run the task-3 guard against the corrected file — it must pass
      without any citation needing the historical marker to hide a live error.

## 5. Gate

- [x] 5.1 `make check` green.
- [x] 5.2 Confirm the architecture test count rose by exactly the number of new
      tests, so none of them silently failed to collect.
- [x] 5.3 Record in `BACKLOG.md` the two limits this change accepts: the
      permissive-`tach`-entry loophole (design, Risks) and the deferred
      question of extending citation-checking to ADRs and `CONSTITUTION.md`
      (design, Open Questions) — the latter joins the existing ADR-trigger
      sweep item rather than opening a second one.
