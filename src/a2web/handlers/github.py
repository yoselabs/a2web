"""GitHub handler — REST API for repo / issue / pull URLs.

Match three URL shapes:
- `github.com/<owner>/<repo>` (and trailing slash) → repo metadata + README
- `github.com/<owner>/<repo>/issues/<n>` → issue + threaded comments
- `github.com/<owner>/<repo>/pull/<n>` → PR + reviews + comments

Auth: `A2WEB_GITHUB_TOKEN` (env-only secret) for the 5000 req/hr rate
limit. Without a token, unauthenticated calls get 60 req/hr per IP.
"""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ..models import Heading, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_GH_HOSTS = frozenset({"github.com", "www.github.com"})
_REPO_PATH_RE = re.compile(r"^/([^/]+)/([^/]+?)/?$")
_ISSUE_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/issues/(\d+)/?$")
_PULL_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)/?$")
_API_BASE = "https://api.github.com"
_TIMEOUT_S = 15.0


def _classify(url: str) -> tuple[str, tuple[str, ...]] | None:
    """Return (kind, parts) for a github URL or None if no match.

    kinds: "repo" → (owner, repo); "issue"/"pull" → (owner, repo, number).
    """
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _GH_HOSTS:
        return None
    path = parsed.path or "/"
    m = _ISSUE_PATH_RE.match(path)
    if m:
        return "issue", m.groups()
    m = _PULL_PATH_RE.match(path)
    if m:
        return "pull", m.groups()
    m = _REPO_PATH_RE.match(path)
    if m:
        # Skip well-known top-level paths that aren't repos.
        if m.group(1) in {"orgs", "settings", "marketplace", "topics", "search"}:
            return None
        return "repo", m.groups()
    return None


class GitHubHandler:
    """Tier-0 handler for github.com repo / issue / pull URLs."""

    name: str = "site_handler:github"

    def matches(self, url: str) -> bool:
        return _classify(url) is not None

    async def fetch(self, url: str, *, state: AppState) -> TierResult:

        classified = _classify(url)
        if classified is None:
            return _empty_result(url, Verdict.not_found)
        kind, parts = classified

        headers = {
            "User-Agent": state.settings.default_ua,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = state.settings.github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True, headers=headers) as client:
                if kind == "repo":
                    return await _fetch_repo(client, url, parts)
                if kind == "issue":
                    return await _fetch_issue(client, url, parts)
                return await _fetch_pull(client, url, parts)
        except httpx.TimeoutException:
            return _empty_result(url, Verdict.timeout)
        except httpx.HTTPError:
            return _empty_result(url, Verdict.connection_error)


async def _fetch_repo(client: httpx.AsyncClient, url: str, parts: tuple[str, ...]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo = parts
    repo_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}")
    if (verdict := _http_verdict(repo_resp)) is not None:
        return _empty_result(url, verdict)
    repo_data = repo_resp.json()

    readme_md = ""
    readme_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/readme")
    if readme_resp.status_code == 200:
        readme_payload = readme_resp.json()
        if isinstance(readme_payload, dict) and readme_payload.get("encoding") == "base64":
            try:
                readme_md = base64.b64decode(readme_payload.get("content", "")).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                readme_md = ""

    rendered = _render_repo(repo_data, readme_md)
    return TierResult(
        body=repo_resp.content,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=dict(repo_resp.headers),
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


async def _fetch_issue(client: httpx.AsyncClient, url: str, parts: tuple[str, ...]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    issue_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}")
    if (verdict := _http_verdict(issue_resp)) is not None:
        return _empty_result(url, verdict)
    issue_data = issue_resp.json()

    comments: list[Any] = []
    comments_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}/comments")
    if comments_resp.status_code == 200:
        loaded = comments_resp.json()
        if isinstance(loaded, list):
            comments = loaded

    rendered = _render_issue(issue_data, comments, kind="Issue")
    return TierResult(
        body=issue_resp.content,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=dict(issue_resp.headers),
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


async def _fetch_pull(client: httpx.AsyncClient, url: str, parts: tuple[str, ...]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    pr_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/pulls/{number}")
    if (verdict := _http_verdict(pr_resp)) is not None:
        return _empty_result(url, verdict)
    pr_data = pr_resp.json()

    reviews: list[Any] = []
    reviews_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/pulls/{number}/reviews")
    if reviews_resp.status_code == 200 and isinstance(loaded := reviews_resp.json(), list):
        reviews = loaded

    comments: list[Any] = []
    comments_resp = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}/comments")
    if comments_resp.status_code == 200 and isinstance(loaded := comments_resp.json(), list):
        comments = loaded

    rendered = _render_pull(pr_data, reviews, comments)
    return TierResult(
        body=pr_resp.content,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=dict(pr_resp.headers),
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


def _http_verdict(resp: httpx.Response) -> Verdict | None:
    """Map non-200 to a closed verdict; return None on 200."""
    if resp.status_code == 200:
        return None
    if resp.status_code == 404:
        return Verdict.not_found
    if resp.status_code == 429:
        return Verdict.rate_limited
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        return Verdict.rate_limited
    return Verdict.connection_error


def _render_repo(data: dict, readme_md: str) -> dict[str, object]:
    full_name = data.get("full_name") or "unknown"
    description = data.get("description") or ""
    stars = data.get("stargazers_count", 0)
    forks = data.get("forks_count", 0)
    language = data.get("language") or "—"
    license_obj = data.get("license") or {}
    license_name = license_obj.get("name") if isinstance(license_obj, dict) else None
    parts = [
        f"# {full_name}\n",
        description + "\n" if description else "",
        f"**★ {stars}** | **Forks {forks}** | **Language** {language}",
        f" | **License** {license_name}" if license_name else "",
        "\n",
    ]
    if readme_md:
        parts.append("\n---\n\n## README\n\n")
        parts.append(readme_md)

    headings: list[Heading] = [Heading(level=1, text=full_name)]
    if readme_md:
        headings.append(Heading(level=2, text="README"))

    return {
        "content_md": "".join(parts).strip() + "\n",
        "title": full_name,
        "byline": data.get("owner", {}).get("login") if isinstance(data.get("owner"), dict) else None,
        "headings": headings,
    }


def _render_issue(data: dict, comments: list, *, kind: str) -> dict[str, object]:
    number = data.get("number")
    title = data.get("title") or "(untitled)"
    user_login = ""
    if isinstance(user := data.get("user"), dict):
        user_login = user.get("login") or ""
    body = data.get("body") or ""
    state_val = data.get("state") or "open"

    parts = [
        f"# {kind} #{number}: {title}\n",
        f"**State:** {state_val}",
        f" | **Author:** {user_login}" if user_login else "",
        "\n\n",
    ]
    if body:
        parts.append(body + "\n\n")
    parts.append("---\n\n## Comments\n\n")
    for c in comments:
        if not isinstance(c, dict):
            continue
        c_user = ""
        if isinstance(c_user_obj := c.get("user"), dict):
            c_user = c_user_obj.get("login") or ""
        c_body = c.get("body") or ""
        if c_body:
            parts.append(f"**{c_user}:**\n\n{c_body}\n\n")

    return {
        "content_md": "".join(parts).strip() + "\n",
        "title": f"{kind} #{number}: {title}",
        "byline": user_login or None,
        "headings": [Heading(level=1, text=f"{kind} #{number}: {title}"), Heading(level=2, text="Comments")],
    }


def _render_pull(data: dict, reviews: list, comments: list) -> dict[str, object]:
    rendered = _render_issue(data, comments, kind="Pull")
    if not reviews:
        return rendered

    parts: list[str] = [str(rendered["content_md"]), "\n## Reviews\n\n"]
    for r in reviews:
        if not isinstance(r, dict):
            continue
        r_user = ""
        if isinstance(r_user_obj := r.get("user"), dict):
            r_user = r_user_obj.get("login") or ""
        r_state = r.get("state") or ""
        r_body = r.get("body") or ""
        parts.append(f"**{r_user}** ({r_state}):\n\n{r_body}\n\n" if r_body else f"**{r_user}** ({r_state})\n\n")

    base_headings = rendered["headings"]
    headings: list[Heading] = []
    if isinstance(base_headings, list):
        for h in base_headings:
            if isinstance(h, Heading):
                headings.append(h)
    headings.append(Heading(level=2, text="Reviews"))

    return {
        "content_md": "".join(parts).strip() + "\n",
        "title": rendered["title"],
        "byline": rendered["byline"],
        "headings": headings,
    }


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
