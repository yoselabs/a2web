"""`INSTALL_BROWSER` — the one fact three documents were describing differently.

**The defect this closes.** Whether the container carries a browser is decided
by a single `Dockerfile` build argument, defaulting to `false` and overridden
to `true` by `release.yml`. That is not hard. What made it hard is that the
fact lived in two build files pytest never opened, so the prose drifted in
BOTH directions at once:

    CLAUDE.md                     "the container ... has no local browser"
    openspec/specs/container-image  Chromium asserted UNCONDITIONALLY
    README.md                     correct, and contradicted by both

All three describe the same `Dockerfile`. An operator reading either of the
first two would have got their deployment wrong — one under-provisioning a
gateway that needs Chromium's system libs, the other expecting browser
escalation from an image that cannot do it.

So this reads the value out of the build files, the way
`test_health_route.py` reads the HEALTHCHECK path out of the Dockerfile, for
the same reason: a fact only stated in a file the test suite never opens is a
fact nothing can hold still.

**What it does NOT do.** It cannot check that the prose is *right* — no test
reads English. It pins the two machine-readable halves so that changing either
one forces the change to be deliberate, and names the documents to update in
its failure message. That is the honest limit, and it is the half that
actually moved.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_DOCKERFILE = _ROOT / "Dockerfile"
_RELEASE = _ROOT / ".github" / "workflows" / "release.yml"

#: `ARG INSTALL_BROWSER=false`, in either build stage.
_ARG_RE = re.compile(r"^\s*ARG\s+INSTALL_BROWSER=(\S+)\s*$", re.MULTILINE)

#: The `build-args:` block entry in the release workflow.
_RELEASE_RE = re.compile(r"^\s*INSTALL_BROWSER=(\S+)\s*$", re.MULTILINE)

_DOCS = "CLAUDE.md (Deployment), openspec/specs/container-image/spec.md, README.md"


def test_the_dockerfile_default_is_browserless() -> None:
    """A plain `docker build` produces the slim image.

    Both stages must agree: the builder stage decides whether the `[browser]`
    extra is resolved into the venv, the runtime stage whether `patchright
    install` runs. A default that diverged between them would produce an image
    carrying one half of the browser rung — the shape that fails at launch
    rather than at build.
    """
    defaults = _ARG_RE.findall(_DOCKERFILE.read_text(encoding="utf-8"))
    assert defaults, "no `ARG INSTALL_BROWSER=` found in the Dockerfile"
    assert set(defaults) == {"false"}, (
        f"`ARG INSTALL_BROWSER` defaults differ or are no longer `false`: {defaults}.\n"
        f"The default IS the documented browserless shape — update {_DOCS} together with it."
    )


def test_both_build_stages_declare_the_arg() -> None:
    """Non-vacuity, and a real trap.

    A `docker build --build-arg` reaches only stages that re-declare the ARG.
    Dropping the second declaration would silently ignore the release
    override in the runtime stage: the venv would carry patchright while
    Chromium was never installed, and the failure surfaces at first browser
    use inside a published image.
    """
    count = len(_ARG_RE.findall(_DOCKERFILE.read_text(encoding="utf-8")))
    assert count >= 2, (
        f"`ARG INSTALL_BROWSER` is declared {count} time(s); each build stage that "
        "uses it must re-declare it, or `--build-arg` does not reach that stage."
    )


def test_the_published_image_overrides_it_to_true() -> None:
    """The release workflow is what makes the published image the browser shape."""
    release = _RELEASE.read_text(encoding="utf-8")
    values = _RELEASE_RE.findall(release)
    assert values == ["true"], (
        f"release.yml no longer passes `INSTALL_BROWSER=true` (found {values!r}).\n"
        "If the published image is deliberately becoming browserless, that is a "
        f"user-visible capability change: update {_DOCS}, and note that browser-only "
        "sites will then return the ADR-0009 incompleteness envelope rather than content."
    )


def test_the_regexes_actually_match_something() -> None:
    """Both patterns are load-bearing; a rename that broke one would leave the
    assertions above vacuously true (`findall` returns `[]`, `set() == {"false"}`
    is False — but `values == ["true"]` would simply fail with an unhelpful
    message, and a future `>= 0`-shaped assertion would pass silently). Prove
    each pattern discriminates."""
    assert _ARG_RE.findall("ARG INSTALL_BROWSER=false\n") == ["false"]
    assert _ARG_RE.findall("ARG INSTALL_CLAUDE_CODE=false\n") == []
    assert _RELEASE_RE.findall("            INSTALL_BROWSER=true\n") == ["true"]
    assert _RELEASE_RE.findall("            SOMETHING_ELSE=true\n") == []
