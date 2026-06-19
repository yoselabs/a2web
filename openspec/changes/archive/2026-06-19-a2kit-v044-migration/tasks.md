# Tasks — a2kit v0.43 → v0.44 migration

A no-op pin bump. The gate is Step 1 (`make check` green with no source edits).
If it goes red, stop — the premise in proposal.md is wrong; re-scope.

---

## Step 0 — Pin bump

- [x] 0a. `pyproject.toml`: dependency spec `a2kit>=0.43,<1` → `a2kit>=0.44,<1`;
  `[tool.uv.sources] a2kit.tag` `v0.43.0` → `v0.44.0`.
- [x] 0b. `uv lock` — refreshed `uv.lock` to v0.44.0 (commit `1f9a7af`).
- [x] 0c. `uv sync --all-extras`. Install clean (a2kit 0.43.0 → 0.44.0).

## Step 1 — Verify (the gate)

- [x] 1a. `make check` — **GREEN with zero source edits.** 845 tests passed,
  coverage 90.02%, lint + ty + arch + tach all clean.
- [x] 1b. Not triggered — gate was green. No re-scope needed.
- [x] 1c. Bare names verified two ways: the existing in-process regression test
  passed in 1a, and the installed binary `a2web list-tools` shows
  `ask`/`fetch_raw`/`refresh` with no `web_*`/`cookies_*` flat names.

## Step 2 — Docs + close-out (only if Step 1 green)

- [x] 2a. `CLAUDE.md`: version strings → v0.44 (lines 9, 13, 15). Surface prose
  untouched; the two v0.42-removal historical citations (lines 108–109) left as-is.
- [x] 2b. `CHANGELOG.md`: added "Changed — a2kit v0.43 → v0.44 (clean no-op pin
  bump)" under `[Unreleased]`.
- [x] 2c. `make install-global` — rebuilt. Tool venv on a2kit 0.44.0; binary
  launches clean (exit 0).
- [ ] 2d. Restart the Claude Code session so Claude picks up the new binary on
  the next session. **(User action — the running session still holds the old
  MCP process.)**

## Explicitly NOT doing (see design.md)

- Internal-spoke adoption (D-Spoke) — not a fit, no job-runner.
- `make bench` (D-Bench) — no extract/envelope/tier change; skip unless 1a is
  behaviorally suspicious.
- `docs/history/A2KIT_FEEDBACK_v0.44.md` (D-Feedback) — v0.44 created no friction.
- Any `src/` edits — if needed, the no-op premise is falsified.

(The change carries one spec delta — a version-agnostic invariant that the MCP
wire contract survives substrate bumps — verified by the existing bare-names
regression test in Step 1c. No new test or source change is needed for it.)
