# Design — a2kit v0.43 → v0.44 migration

This is a version-bump migration. The "design" is mostly the evidence that it
*is* a no-op, plus three small decisions.

## Evidence the bump is a no-op

Captured during exploration (a2kit local clone at `~/Workspaces/a2kit`, tags
`v0.43.0`..`v0.44.0`):

1. **Top-level public surface unchanged.** `git diff v0.43.0 v0.44.0 --
   src/a2kit/__init__.py` is empty.
2. **a2web's import set is narrow and untouched.** a2web imports only:
   `a2kit` (top level), `a2kit.log`, `a2kit.Lazy`, `a2kit.packages.formatter`
   (`PruneEmpty`, `tsv.encode_tsv`). None appear in v0.44's changed/removed list.
3. **The churned files are auth + serve/spoke/http** — surfaces a2web does not
   import. The four a2web-adjacent files (`app.py`, `routers.py`, `tool.py`,
   `di/container.py`) changed **docstrings only**, except di's legacy-method
   error type (`TypeError` → `AttributeError`) on names a2web never calls.
4. **LDD is byte-identical.** `git diff --quiet v0.43.0 v0.44.0 --
   src/a2kit/log.py` → IDENTICAL. Two LDD-token diffs total, both docstring
   deletions.
5. **Transport.** a2web is wired into Claude Code as a stdio server
   (`command: …/a2web`, `args: ["serve"]`). The BREAKING http-multiplex change
   only affects `--transport=http`, which a2web never sets. stdio unchanged.

## D-Spoke — do not adopt the internal spoke

v0.44's headline feature (ADR 0029) is a private-UDS spoke so first-party
**sandboxed jobs** can reach a **single-writer core** without traversing public
edge auth, plus `TokenAuth` for per-request lease validation.

a2web is a stateless web-fetch server: no job-runner, no single-writer core, no
lease table. The spoke solves a problem a2web does not have. Adopting it would
add unused surface against the Constitution's magic budget. **Decision: skip.**
(Revisit only if a2web ever grows a sandboxed-job execution model.)

## D-Bench — no bench run by default

`make bench` is live-network + spends LLM quota; CLAUDE.md says run it after
changes that could move output quality/cost (envelope shape, extraction, tier
routing, handlers, `next_links`). v0.44 changes none of those for a2web — it is a
pin bump with no source edits. **Decision: skip bench** unless `make check`
surfaces something behavioral (it shouldn't). Run manually only if curious.

## D-Feedback — no outgoing feedback round by default

The repo keeps `docs/history/A2KIT_FEEDBACK_v0.*.md` rounds when a2kit's surface
created friction. v0.44 created none — nothing a2web consumes changed, the
migration is frictionless by construction. **Decision: no feedback file.** A
one-line note in `CHANGELOG.md` ("v0.44 was a clean no-op bump") suffices.

## Migration order

Trivial and linear (no load-bearing ordering like v0.43 had):

1. Bump pin in `pyproject.toml` (spec range + `[tool.uv.sources]` tag).
2. `uv lock` + `uv sync --all-extras`.
3. `make check` — **expected green, no source edits.** This is the gate.
4. If green: docs (`CLAUDE.md` version strings, `CHANGELOG.md`) +
   `make install-global` + session restart.
5. If red: stop. The no-op premise is falsified; re-scope as a real migration.
