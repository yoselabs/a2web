"""A GitHub section that could NOT be retrieved must not read as empty-at-source.

Six sites in `github.py` swallowed a `GitHubException` from a *supplementary*
call and continued with `None`, which the renderer then treated as an empty
list. An issue whose comments were rate-limited and an issue with genuinely
zero comments produced byte-identical output: a `## Comments` heading with
nothing under it.

That is the ADR-0009 harm in miniature — a2web knew the section was missing,
and told the caller something that reads as complete. The fix does not fail the
whole fetch (the primary object WAS retrieved and is useful); it marks the
section unretrieved in the body and attaches an operator hint naming it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from a2web.handlers import GitHubHandler
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR

#: GitHub answers an exhausted quota with 403 + `x-ratelimit-remaining: 0`,
#: which gidgethub raises as `RateLimitExceeded` — a `GitHubException`.
_RATE_LIMITED_HEADERS = {
    "content-type": "application/json",
    "x-ratelimit-remaining": "0",
    "x-ratelimit-limit": "60",
    "x-ratelimit-reset": "9999999999",
}


def _state() -> AppState:
    return make_default_state(settings=AppSettings(github_token=""))


def _rate_limited() -> FakeCurlResp:
    return FakeCurlResp(
        403,
        text=json.dumps({"message": "API rate limit exceeded"}),
        headers=_RATE_LIMITED_HEADERS,
    )


@pytest.mark.asyncio
async def test_rate_limited_comments_are_not_rendered_as_no_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing case: the primary object survives, the section is honest."""
    issue_data = json.loads((_FIX / "github_issue.json").read_text())

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if url.endswith("/comments"):
            return _rate_limited()
        return FakeCurlResp(200, text=json.dumps(issue_data))

    patch_curl_session(monkeypatch, _fake_get)

    result = await GitHubHandler().fetch(
        "https://github.com/octocat/Hello-World/issues/42",
        state=_state(),
    )

    # The primary object was retrieved — failing the whole fetch would be worse.
    assert result.verdict == Verdict.ok
    assert "Issue #42" in result.pre_rendered.title

    body = result.pre_rendered.content_md
    assert "not retrieved" in body.lower(), (
        "the Comments section was rate-limited but renders indistinguishably "
        f"from an issue with zero comments:\n{body}"
    )

    hint = result.operator_hint
    assert hint is not None, "an unretrieved section must carry an operator hint"
    assert hint.code == "section_unretrieved"
    assert "comments" in hint.message.lower(), f"the hint must name the section: {hint.message}"


@pytest.mark.asyncio
async def test_a_genuinely_empty_section_emits_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-vacuity for the fix: absence-because-empty stays quiet.

    Without this, marking every section unretrieved would pass the test above
    while making the hint meaningless.
    """
    issue_data = json.loads((_FIX / "github_issue.json").read_text())

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if url.endswith("/comments"):
            return FakeCurlResp(200, text="[]")
        return FakeCurlResp(200, text=json.dumps(issue_data))

    patch_curl_session(monkeypatch, _fake_get)

    result = await GitHubHandler().fetch(
        "https://github.com/octocat/Hello-World/issues/42",
        state=_state(),
    )

    assert result.verdict == Verdict.ok
    assert result.operator_hint is None, "a genuinely empty section is not a degradation"
    assert "not retrieved" not in result.pre_rendered.content_md.lower()


@pytest.mark.asyncio
async def test_a_rate_limited_readme_does_not_abort_the_repo_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`github.py:226` caught only `BadRequest` where four siblings catch
    `GitHubException` — so a rate-limited README aborted the WHOLE repo fetch.

    The opposite failure from the other five: over-failing where they
    under-fail. Same family, same commit.
    """
    repo_data = json.loads((_FIX / "github_repo.json").read_text())

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if url.endswith("/readme"):
            return _rate_limited()
        if "/issues" in url or "/pulls" in url:
            return FakeCurlResp(200, text="[]")
        return FakeCurlResp(200, text=json.dumps(repo_data))

    patch_curl_session(monkeypatch, _fake_get)

    result = await GitHubHandler().fetch("https://github.com/octocat/Hello-World", state=_state())

    assert result.verdict == Verdict.ok, "a missing README must not sink the repo fetch"
    assert result.pre_rendered.title == "octocat/Hello-World"
    hint = result.operator_hint
    assert hint is not None and "readme" in hint.message.lower(), (
        "the README could not be retrieved; say so rather than rendering a repo with no README"
    )


@pytest.mark.asyncio
async def test_several_unretrieved_sections_are_named_in_one_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PR fetches reviews AND comments; both can degrade in the same fetch.

    `TierResult.operator_hint` is singular, so the sections ride in one hint's
    message rather than growing a hint code per section.
    """
    pr_data = {"number": 7, "title": "Add feature", "body": "X.", "state": "open", "user": {"login": "alice"}}

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if "/reviews" in url or "/comments" in url:
            return _rate_limited()
        return FakeCurlResp(200, text=json.dumps(pr_data))

    patch_curl_session(monkeypatch, _fake_get)

    result = await GitHubHandler().fetch(
        "https://github.com/octocat/Hello-World/pull/7",
        state=_state(),
    )

    assert result.verdict == Verdict.ok
    hint = result.operator_hint
    assert hint is not None
    message = hint.message.lower()
    assert "reviews" in message and "comments" in message, (
        f"both degraded sections must be named, got: {hint.message}"
    )
