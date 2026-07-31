"""`_fetch_old_reddit` must not report an interstitial as the thread.

It GETs HTML and runs trafilatura exactly as `twitter.py` and `wikipedia.py`
do — but unlike both siblings it never ran the shared `challenge_verdict`
check, so anything that extracted to prose came back `Verdict.ok`. A wall page
extracts perfectly well.

Both fixtures are CAPTURED from old.reddit.com on 2026-07-31, never
hand-written: a hand-written wall fixture encodes the same assumption as the
detector that reads it, authored by the same person at the same moment, so it
cannot falsify anything.

The captures also surfaced a second defect the fix depends on. The catalogue
already carried `whoa there, pardner`, but only in the branch gated below
`LENGTH_FLOOR` — and Reddit's block page extracts to 779 characters. So adding
the `challenge_verdict` call ALONE would have shipped a check that did not
catch the page it was written for, and this suite would have stayed red. That
is the "wordier interstitial from the same family still reads as content" limit
the catalogue's own comment states.
"""

from __future__ import annotations

from typing import Any

import pytest

from a2web.handlers._common import challenge_verdict
from a2web.handlers.reddit import _fetch_old_reddit
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_CAPTURED = FIXTURES_DIR / "captured"
_NETWORK_POLICY_BLOCK = _CAPTURED / "old_reddit_network_policy_block.html"
_OVER_18_GATE = _CAPTURED / "old_reddit_over18_interstitial.html"


def _state() -> AppState:
    return make_default_state(settings=AppSettings())


def _extract(html: str) -> str:
    import trafilatura

    return trafilatura.extract(html, output_format="markdown", include_comments=True, include_tables=False) or ""


@pytest.mark.parametrize(
    ("name", "path"),
    [("network policy block", _NETWORK_POLICY_BLOCK), ("over-18 gate", _OVER_18_GATE)],
)
def test_captured_interstitials_are_recognised_as_walls(name: str, path: Any) -> None:
    """The catalogue must see both captures as walls, ABOVE the length floor.

    Anti-vacuity for the fixtures themselves: each must still extract to real
    prose. A capture that decayed to an empty extraction would make the handler
    test below pass through the thinness path instead of the wall path, proving
    nothing about wall detection.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    markdown = _extract(html)

    assert len(markdown) > 500, (
        f"{name} extracts to {len(markdown)} chars — at or under LENGTH_FLOOR the "
        "length-gated branch would catch it and this test would no longer be "
        "exercising the above-the-floor path that made it slip through"
    )
    assert challenge_verdict(html, content_md=markdown) is not None, (
        f"{name} is a wall the catalogue does not recognise; it extracts to {len(markdown)} chars of plausible prose:\n{markdown[:300]}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "path"),
    [("network policy block", _NETWORK_POLICY_BLOCK), ("over-18 gate", _OVER_18_GATE)],
)
async def test_old_reddit_reports_an_interstitial_as_a_wall(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    path: Any,
) -> None:
    """Served at HTTP 200, an interstitial must not come back as the thread.

    200 is the load-bearing status: a 403 already leaves via the non-ok branch,
    so it is the *fake 200* — a wall the transport reports as a success — that
    the verdict check exists for. The over-18 capture was served at 200 by
    old.reddit itself.
    """
    html = path.read_text(encoding="utf-8", errors="replace")

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        return FakeCurlResp(200, text=html, content_type="text/html")

    patch_curl_session(monkeypatch, _fake_get)

    # `_fetch_old_reddit` directly, not `RedditHandler().fetch`. The public entry
    # tries the RSS surface first, and a non-Atom body fails `_parse_atom` into
    # `content_type_mismatch` — so a test through the front door goes green
    # without the HTML fallback ever running, which is the wrong reason.
    result = await _fetch_old_reddit(
        "https://www.reddit.com/r/LocalLLaMA/comments/1abcxyz/some_thread/",
        state=_state(),
    )

    assert result.verdict != Verdict.ok, (
        f"the {name} interstitial was reported as a successfully fetched thread; "
        f"content_md began: {(result.pre_rendered.content_md if result.pre_rendered else '')[:200]!r}"
    )
