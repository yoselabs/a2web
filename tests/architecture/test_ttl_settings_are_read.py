"""Every declared TTL setting is read by at least one code path.

`cache_ttl_live_m` sat in `AppSettings` for months, documented, tunable via
`A2WEB_CACHE_TTL_LIVE_M` — and read by nothing. An operator could set it, see no
error, and get no effect. That is worse than a missing setting: a missing one
fails visibly, a dead one silently reports that it worked.

It is also the exact shape `_ttl_for`'s old `getattr(settings_obj, ...,
<literal>)` could have produced on any rename — the read would fall back to the
duplicated literal and the setting would go dead while still looking wired.

Scoped to TTLs rather than every setting because that is where the failure was
found and where the cost is a silently stale answer. Widening it later is
welcome; asserting nothing today would not be.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

_MIN_FILES = 20

# A floor, not a frozen list: the guard must have found the settings it knows
# about, or the walk is broken and the whole check reads green on nothing.
_KNOWN_TTL_SETTINGS = frozenset({"cache_ttl_static_h", "cache_ttl_article_h", "cache_ttl_live_m", "extraction_cache_ttl_s"})


def _declared_ttl_settings() -> set[str]:
    """TTL field names declared on `AppSettings`."""
    tree = ast.parse((SRC_ROOT / "settings.py").read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "AppSettings")
    return {
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and "ttl" in node.target.id.lower()
    }


def test_every_declared_ttl_setting_is_read_somewhere() -> None:
    declared = _declared_ttl_settings()
    assert _KNOWN_TTL_SETTINGS <= declared, (
        f"the walk did not find the known TTL settings (found {sorted(declared)}). The parse broke — fix it rather than lowering the floor."
    )

    read: set[str] = set()
    for path in walked_files(SRC_ROOT, minimum=_MIN_FILES):
        if path.name == "settings.py":
            continue  # the declaration is not a read
        source = path.read_text(encoding="utf-8")
        read |= {name for name in declared if name in source}

    dead = sorted(declared - read)
    assert not dead, (
        f"TTL setting(s) declared but never read: {dead}. An operator can set "
        "these, see no error, and get no effect — which reports success while "
        "doing nothing. Wire it up or delete it."
    )


def test_the_guard_can_tell_read_from_unread() -> None:
    """Anti-vacuity: a substring search that matches everything proves nothing.

    A name that appears in NO source file must be reported as dead, or the check
    above would pass for any input.
    """
    invented = "cache_ttl_a_setting_that_does_not_exist_h"
    hits = [p.name for p in walked_files(SRC_ROOT, minimum=_MIN_FILES) if invented in p.read_text(encoding="utf-8")]
    assert not hits, f"the fixture name was found in {hits} — pick a different one"
