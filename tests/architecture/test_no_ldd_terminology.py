"""Architectural invariant: the retired "LDD" branding does not appear in live
a2web source.

The `a2kit.ldd` module was removed in a2kit v0.42 (ADR-0027); a2web's logging is
now plain `a2kit.log`. The lingering "LDD" term (in comments, docstrings, and the
old `_ldd_ambient` helper name) pointed at a subsystem that no longer exists and
confused "it's just structured logging" with bespoke machinery. This rule keeps
it from creeping back into `src/a2web/`.

Scope is `src/a2web/` only — CLAUDE.md retains a couple of *factual* references
that name a2kit's removed `a2kit.ldd` API (a migration-history pointer and a
never-use guard); those reinforce that the subsystem is gone and are exempt by
design. Dated `docs/history/` records are likewise out of scope.

Companion to `test_no_rogue_structlog`.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"

# Case-insensitive standalone-ish "ldd" token: the camelCase/identifier/word
# uses we care about (LDD, _ldd_, LddSink, a2kit.ldd, ldd_state) all have a
# non-lowercase-letter on at least one side. No common English word contains
# the substring "ldd", so false positives are effectively nil; add here if one
# ever surfaces.
_LDD = re.compile(r"(?<![a-zA-Z])ldd|ldd(?![a-z])|Ldd", re.IGNORECASE)
_ALLOWLIST: frozenset[str] = frozenset()


def test_no_ldd_terminology_under_src() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if _LDD.search(line) and line.strip() not in _ALLOWLIST:
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert not violations, (
        'Retired "LDD" branding found under src/a2web/ — a2web logging is plain '
        "`a2kit.log` now; describe it as logging / typed events:\n  " + "\n  ".join(violations)
    )
