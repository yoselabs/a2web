"""Every package is inside the boundary rule, and every rule has a package.

`tach.toml` enforces "packages may not import from `a2web.<domain>`" — and it
genuinely does, for the modules it lists. That was verified by injection: adding
`from a2web.settings import AppSettings` to `packages/block_detector.py` fails
`tach check` with a precise message.

The defect is coverage, not the tool. The module list is hand-maintained, and
both directions of drift are silent:

  * **A package with no entry has no contract at all.** It inherits the
    permissive parent `a2web` module, which may import domain code freely.
    Verified 2026-07-27: a temporary package under `packages/` importing
    `a2web.settings` — the exact violation the invariant exists to prevent —
    passed `tach check` cleanly. Adding a package is precisely the moment the
    contract matters, and precisely the moment it is easiest to forget.
  * **A listed module that no longer exists degrades to a warning.** `tach`
    prints `[WARN] Module containing '…' not found in project` and exits 0.
    `ndjson_log` sat retired in the config emitting that line on every single
    test run until this guard was written, which is the proof that a warning in
    this position is indistinguishable from noise.

This is a different failure from the one `_walk.walked_files(minimum=…)`
defends against. That protects a guard that scans *nothing*; this one scanned
plenty, it just did not scan the subject. A floor cannot catch a guard that has
been scoped away from what it was written to cover.

**What this does NOT check.** It answers "does a contract exist for this
package", not "is that contract tight". A module listed with permissive
`depends_on` passes here while granting no real protection. Tightening the
entries is a separate question that needs a survey of what they declare today —
see the change's design, Open Questions. Claiming more than this would be the
same over-trust the guard exists to correct.
"""

from __future__ import annotations

import tomllib

from ._walk import REPO_ROOT, SRC_ROOT

_PACKAGES_ROOT = SRC_ROOT / "packages"
_TACH_CONFIG = REPO_ROOT / "tach.toml"

#: Module path prefix under which every in-tree package must be declared.
_PACKAGE_PREFIX = "a2web.packages."

#: Names under `packages/` that are not packages.
_NOT_PACKAGES = frozenset({"__init__.py", "__pycache__", "README.md"})

#: Floors for both sides of the comparison. Two empty sets are trivially equal,
#: so without these the guard passes loudest exactly when it is most broken —
#: a moved source root or an unparseable config.
_MIN_PACKAGES = 3
_MIN_CONFIGURED = 3


def _real_packages() -> set[str]:
    assert _PACKAGES_ROOT.is_dir(), f"packages root does not exist: {_PACKAGES_ROOT}"
    found = {
        _PACKAGE_PREFIX + (child.stem if child.suffix == ".py" else child.name)
        for child in _PACKAGES_ROOT.iterdir()
        if child.name not in _NOT_PACKAGES and not child.name.startswith((".", "_")) and (child.is_dir() or child.suffix == ".py")
    }
    assert len(found) >= _MIN_PACKAGES, (
        f"found {len(found)} package(s) under {_PACKAGES_ROOT}, expected at least "
        f"{_MIN_PACKAGES}. The source root moved or the tree shrank below the floor. "
        "Do NOT lower the floor to make this pass — an empty side makes the "
        "comparison below vacuous."
    )
    return found


def _configured_packages() -> set[str]:
    assert _TACH_CONFIG.is_file(), f"boundary config not found: {_TACH_CONFIG}"
    config = tomllib.loads(_TACH_CONFIG.read_text(encoding="utf-8"))
    found = {m["path"] for m in config.get("modules", []) if m.get("path", "").startswith(_PACKAGE_PREFIX)}
    assert len(found) >= _MIN_CONFIGURED, (
        f"parsed {len(found)} package module(s) out of {_TACH_CONFIG.name}, expected at "
        f"least {_MIN_CONFIGURED}. The config's schema changed and this guard is no "
        "longer reading it — fix the parse, do not lower the floor."
    )
    return found


def test_both_sides_of_the_comparison_are_populated() -> None:
    """Neither set may be empty — equal-and-empty is the vacuous pass."""
    _real_packages()
    _configured_packages()


def test_every_package_has_a_boundary_contract() -> None:
    unlisted = _real_packages() - _configured_packages()
    assert not unlisted, (
        "packages with NO module-boundary contract:\n"
        + "".join(f"  {name}\n" for name in sorted(unlisted))
        + "\nAn unlisted package inherits the permissive parent `a2web` module and "
        "may import domain code freely — `tach check` will pass while the invariant "
        "is unenforced. Add a `[[modules]]` entry with the dependencies it genuinely "
        "needs (usually `depends_on = []`)."
    )


def test_every_boundary_contract_has_a_package() -> None:
    stale = _configured_packages() - _real_packages()
    assert not stale, (
        "module-boundary entries naming packages that do not exist:\n"
        + "".join(f"  {name}\n" for name in sorted(stale))
        + "\n`tach` reports these as a warning and still exits 0, so they rot "
        "invisibly — and a package RENAMED rather than deleted silently loses its "
        "contract this way. Remove the entry, or fix the path if the package moved."
    )
