"""GitHub handler tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from a2web.handlers import GitHubHandler, match_handler
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState, build_state

_FIX = Path(__file__).parent / "fixtures"


def _state(token: str = "") -> AppState:
    return build_state(settings=AppSettings(github_token=token))


def test_match_handler_returns_github_for_repo() -> None:
    h = match_handler("https://github.com/octocat/Hello-World")
    assert isinstance(h, GitHubHandler)


def test_github_matches_repo_with_trailing_slash() -> None:
    assert GitHubHandler().matches("https://github.com/octocat/Hello-World/")


def test_github_matches_issue() -> None:
    assert GitHubHandler().matches("https://github.com/octocat/Hello-World/issues/42")


def test_github_matches_pull() -> None:
    assert GitHubHandler().matches("https://github.com/octocat/Hello-World/pull/7")


def test_github_does_not_match_org_url() -> None:
    assert not GitHubHandler().matches("https://github.com/orgs/anthropics/teams")


def test_github_does_not_match_marketplace() -> None:
    assert not GitHubHandler().matches("https://github.com/marketplace")


def test_github_does_not_match_blob() -> None:
    # blob/<sha>/path is too deep for the repo regex; not classified as repo.
    assert not GitHubHandler().matches("https://github.com/octocat/Hello-World/blob/main/README.md")


@pytest.mark.asyncio
async def test_github_repo_renders_metadata_and_readme(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_data = json.loads((_FIX / "github_repo.json").read_text())
    readme_md = "# Hello\n\nWelcome to my repo."
    readme_payload = {"encoding": "base64", "content": base64.b64encode(readme_md.encode()).decode()}

    captured_urls: list[str] = []

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_urls.append(url)
        if url.endswith("/readme"):
            return httpx.Response(200, text=json.dumps(readme_payload))
        return httpx.Response(200, text=json.dumps(repo_data))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/octocat/Hello-World", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre.title == "octocat/Hello-World"
    assert "1234" in pre.content_md  # stars
    assert "MIT License" in pre.content_md
    assert "Welcome to my repo" in pre.content_md
    assert any("/repos/octocat/Hello-World" in u for u in captured_urls)
    assert any("/readme" in u for u in captured_urls)


@pytest.mark.asyncio
async def test_github_issue_renders_threaded_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    issue_data = json.loads((_FIX / "github_issue.json").read_text())
    comments = [
        {"user": {"login": "bob"}, "body": "I have the same issue."},
        {"user": {"login": "carol"}, "body": "Workaround: do Z."},
    ]

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if url.endswith("/comments"):
            return httpx.Response(200, text=json.dumps(comments))
        return httpx.Response(200, text=json.dumps(issue_data))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/octocat/Hello-World/issues/42", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert "Issue #42: Fix the thing" in pre.title
    assert "alice" in pre.content_md
    assert "bob" in pre.content_md
    assert "carol" in pre.content_md


@pytest.mark.asyncio
async def test_github_pull_renders_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    pr_data = {"number": 7, "title": "Add feature", "body": "This adds X.", "state": "open", "user": {"login": "alice"}}
    reviews = [{"user": {"login": "bob"}, "state": "APPROVED", "body": "LGTM"}]

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if "/pulls/7/reviews" in url:
            return httpx.Response(200, text=json.dumps(reviews))
        if "/issues/7/comments" in url:
            return httpx.Response(200, text=json.dumps([]))
        return httpx.Response(200, text=json.dumps(pr_data))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/octocat/Hello-World/pull/7", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert "Pull #7: Add feature" in pre.title
    assert "Reviews" in pre.content_md
    assert "APPROVED" in pre.content_md


@pytest.mark.asyncio
async def test_github_token_sent_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_headers: list[dict[str, str]] = []

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_headers.append(dict(self.headers))
        return httpx.Response(200, text='{"full_name": "x/y", "owner": {"login": "x"}}')

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    await GitHubHandler().fetch("https://github.com/x/y", state=_state(token="ghp_test"))  # noqa: S106
    assert any(h.get("authorization", "").lower() == "bearer ghp_test" for h in captured_headers)


@pytest.mark.asyncio
async def test_github_no_token_no_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_headers: list[dict[str, str]] = []

    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_headers.append(dict(self.headers))
        return httpx.Response(200, text='{"full_name": "x/y", "owner": {"login": "x"}}')

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    await GitHubHandler().fetch("https://github.com/x/y", state=_state(token=""))
    assert all("authorization" not in h for h in captured_headers)


@pytest.mark.asyncio
async def test_github_429_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(429, text="")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/x/y", state=_state())
    assert result.verdict == Verdict.rate_limited


@pytest.mark.asyncio
async def test_github_403_with_zero_remaining_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(403, text="rate limited", headers={"x-ratelimit-remaining": "0"})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/x/y", state=_state())
    assert result.verdict == Verdict.rate_limited


@pytest.mark.asyncio
async def test_github_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(404, text="")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    result = await GitHubHandler().fetch("https://github.com/x/missing", state=_state())
    assert result.verdict == Verdict.not_found
