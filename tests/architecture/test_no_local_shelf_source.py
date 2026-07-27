"""No shelf dependency resolves to a local working copy.

Developing against an unreleased shelf change means repointing a dependency at
a local checkout (`{ path = "../shelf/packages/foo" }` or an editable install).
Committing that state breaks the build for everyone else and for CI, because
the path does not exist there — so the shelf loop forbids it.

**The existing protection fails open.** `.git/hooks/pre-commit` resolves the
real check out of a shelf clone:

    GUARD="$SHELF/tools/hooks/forbid-local-shelf-source.py"
    [ -f "$GUARD" ] && exec python3 "$GUARD"
    exit 0   # guard unavailable (shelf not cloned) -> do not block

That `exit 0` is correct *in the hook* — a hook that hard-failed without the
shelf would block every commit on a fresh clone of any consumer. But it means
the protection exists only on a machine that already has the shelf at the
expected path, and the installer that puts the hook there lives in the shelf,
not in this repo. So a fresh clone, and every CI runner, had none of it — while
the project's own instructions described it as a hard block.

This check closes that gap from the other side. CI runs `make check`, so a test
here is enforced on every push regardless of local setup. The hook stays as it
is: it catches the mistake earlier and more cheaply, and this is the floor
under it.

**Reads the manifest, not the environment.** The violation is what gets
committed, and that is `pyproject.toml`. Inspecting installed distributions
instead would flag a developer's legitimately-editable local environment that
was never committed — punishing exactly the workflow the hook is designed to
permit.
"""

from __future__ import annotations

import tomllib

from ._walk import REPO_ROOT

_PYPROJECT = REPO_ROOT / "pyproject.toml"

#: Keys in a `[tool.uv.sources]` entry that resolve to a local working copy
#: rather than a pinned remote revision.
_LOCAL_KEYS = ("path", "editable", "workspace")

#: The source table must carry at least this many pinned entries. Population is
#: 13; the floor exists so a renamed or restructured table fails loudly instead
#: of finding nothing to object to and reporting green.
_MIN_SOURCES = 8


def _sources() -> dict[str, dict]:
    config = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    sources = config.get("tool", {}).get("uv", {}).get("sources", {})
    assert len(sources) >= _MIN_SOURCES, (
        f"parsed {len(sources)} dependency source(s) from {_PYPROJECT.name}, expected "
        f"at least {_MIN_SOURCES}. The source table moved or was renamed and this "
        "guard is no longer reading it — fix the parse, do not lower the floor."
    )
    return sources


def test_the_source_table_is_populated() -> None:
    """A guard that found no sources cannot object to any of them."""
    _sources()


def test_no_dependency_resolves_to_a_local_working_copy() -> None:
    offenders = [f"  {name}: {key} = {spec[key]!r}" for name, spec in _sources().items() for key in _LOCAL_KEYS if key in spec]
    assert not offenders, (
        "dependencies pointing at a local working copy:\n"
        + "\n".join(offenders)
        + "\n\nThis builds only on the machine that has that path. Repoint at a "
        "pinned tag before committing:\n"
        '    name = { git = "https://github.com/yoselabs/shelf", '
        'subdirectory = "packages/name", tag = "name-vX.Y.Z" }\n'
        "If the change you are testing is not released yet, release it on the shelf "
        "first — that ordering is the point of the rule, not an obstacle to it."
    )
