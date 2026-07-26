"""The dead-rung guard's decision logic — deterministic, runs in the DEFAULT gate.

This file is deliberately NOT `browser`-marked. Its subject is the skip→fail
policy (`browser_unavailable_policy`), not any real engine, so it needs no
Chromium and runs in `make check` on every commit.

Why it can't live in `test_browser_smoke.py`: that module is `browser`-marked
and therefore deselected from the default gate, AND the FAIL branch it guards is
one a *working* browser can never exercise — a real launch succeeds, so the
"required but absent" path never fires even in the CI browser lane. The only way
to keep that branch honest is a deterministic test, in the gate, that forces
`required=True` with no browser in sight. Precisely the branch that stayed
plausible-looking while the zendriver robust rung shipped dead-on-launch.
"""

from __future__ import annotations

import pytest

from tests.capabilities.browser_tier.test_browser_smoke import browser_unavailable_policy


def test_skips_when_browser_not_required() -> None:
    """Dev laptop (flag unset): a missing engine is a humane skip, not a failure."""
    with pytest.raises(pytest.skip.Exception):
        browser_unavailable_policy("no chromium on this dev machine", required=False)


def test_fails_when_browser_required() -> None:
    """CI browser lane (flag set): a missing engine is a HARD FAILURE, never a
    skip. This assertion would have gone red the day the zendriver rung could
    not launch — it is the witness the release gate structurally lacked."""
    with pytest.raises(pytest.fail.Exception):
        browser_unavailable_policy("engine did not launch", required=True)
