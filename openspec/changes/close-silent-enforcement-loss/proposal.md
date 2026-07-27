## Why

Three of this repo's stated invariants are not actually enforced, and each
failure is silent by construction. They were found by spiking, not by a test
going red — which is the point: every one of them is a check that cannot fail.

This is the repo's own recurring failure mode, already stated in `CLAUDE.md`
("never add a structural guard without an assertion that it found something")
and already paid for twice — 30 of 32 architecture tests passing against an
empty source tree, and `test_tools_return_pydantic_not_str` staying green
through the whole a2kit sunset while matching a decorator that no longer
existed. These three are the same shape at a different layer: not a guard that
scans nothing, but a guard whose *scope* silently stopped covering the thing it
names.

Each was verified empirically, not inferred:

1. **A new package gets no boundary contract.** `tach.toml`'s module list is
   hand-maintained. A temporary package under `src/a2web/packages/` importing
   `a2web.settings` — the exact violation the invariant exists to prevent —
   passed `tach check` cleanly, because it was not listed. Conversely a listed
   module that no longer exists degrades to `[WARN] … not found in project` and
   still exits 0. That warning is live today: `ndjson_log` was retired and has
   been printing on every single test run since, which is the proof that a
   warning in this position is indistinguishable from noise.

2. **`CLAUDE.md` cites four things that do not exist.** It is the first file
   every agent reads and the map they navigate by: `src/a2web/_plugin.py`
   (promoted to the shelf as `plugin_surface`),
   `tests/test_packages_independence.py` (deleted — `tach.toml` took over),
   `tools/hooks/install.py` (lives in the shelf, never in this repo), and
   `ndjson_log` listed among the current packages. An agent that trusts the map
   looks for an enforcement mechanism that isn't there, or worse, believes an
   invariant is covered when it is not — exactly what happened with #1.

3. **The no-local-shelf-source commit guard fails open.**
   `.git/hooks/pre-commit` resolves the guard out of a shelf clone and
   `exit 0`s when it cannot find one. The installer is not in this repo. So a
   fresh clone, a CI runner, and any machine without the shelf at the expected
   path have **no protection at all**, while `CLAUDE.md` states the block as a
   fact ("the commit guard installed via `tools/hooks/install.py` blocks it").
   A fail-open guard advertised as fail-closed is worse than no guard, because
   it is trusted.

Now, because #1 and #3 are one `git add` away from shipping a broken boundary
or a local `path=` dependency, and because CI runs `make check` — so a
test-suite guard is genuinely enforced on every push, unlike a git hook.

## What Changes

- **New: tach module-list coverage guard.** A test asserting the module list in
  `tach.toml` and the real package tree under `src/a2web/packages/` describe the
  same set — in both directions. A new package with no entry fails; a stale
  entry fails instead of warning.
- **New: local-shelf-source guard.** A test asserting no shelf dependency in
  `pyproject.toml` resolves to a local `path=` or editable source. This moves
  the invariant from a machine-local, fail-open git hook into the gate CI
  actually runs.
- **New: `CLAUDE.md` citation guard.** A test asserting that the repo-relative
  paths `CLAUDE.md` cites as current resolve, with an explicit convention for
  the legitimate historical mention (`packages/http_cache.py` *was* the old
  home — that sentence must stay writable).
- **Corrected: the four stale `CLAUDE.md` citations**, and the retired
  `ndjson_log` entry removed from `tach.toml`.
- Not changed: the git hook itself. It lives in the shelf and its fail-open
  behaviour is defensible there (a hook that hard-fails without the shelf would
  block every commit on a fresh clone). The fix is to stop *relying* on it
  alone, and to stop describing it as a hard block.

## Capabilities

### New Capabilities

- `enforcement-integrity`: the requirement that a stated structural invariant is
  actually enforced over its full stated scope — covering guard-scope coverage
  (every subject a rule names is inside the mechanism that enforces it), the
  ban on fail-open enforcement being described as fail-closed, and the accuracy
  of the agent-facing architecture map.

### Modified Capabilities

None. No product behaviour, wire shape, or tool signature changes; this is
enforcement of existing invariants, not new ones.

## Impact

- **Code:** `tach.toml` (drop the retired `ndjson_log` module), `CLAUDE.md`
  (four corrections), three new tests under `tests/architecture/`.
- **Gate:** `make check` gains three tests. Each must be verified red before
  green against an injected violation, per the repo's own anti-vacuity rule —
  the failure mode being fixed here is precisely a guard nobody watched fail.
- **No runtime impact.** Nothing in `src/a2web/` changes behaviour; no
  dependency is added or moved.
- **Risk:** the `CLAUDE.md` citation guard is the one that could become
  annoying — it constrains how the project's most-edited prose file names
  files. The design must make the historical-mention escape hatch obvious, or
  it will be worked around rather than satisfied.
