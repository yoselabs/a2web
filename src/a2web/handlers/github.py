"""GitHub handler — REST API for repo / issue / pull URLs.

Match three URL shapes:
- `github.com/<owner>/<repo>` (and trailing slash) → repo metadata + README
- `github.com/<owner>/<repo>/issues/<n>` → issue + threaded comments
- `github.com/<owner>/<repo>/pull/<n>` → PR + reviews + comments

Auth: `A2WEB_GITHUB_TOKEN` (env-only secret) for the 5000 req/hr rate
limit. Without a token, unauthenticated calls get 60 req/hr per IP.

v0.16: the REST plumbing (URL templates, base64 README unwrap, Link-header
pagination, `X-RateLimit-Remaining: 0` detection) moves to `gidgethub`.
gidgethub is sans-IO — its `_request` hook is bound to a curl_cffi transport
adapter so the handler keeps inheriting our retries / breakers / proxy logic.
Markdown rendering stays here byte-equivalent to v0.15.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import gidgethub
from gidgethub.abc import GitHubAPI

from ..models import Heading, NextLink, Verdict
from ..packages.http_fetch import FetchVerdict, fetch_bytes

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_GH_HOSTS = frozenset({"github.com", "www.github.com"})
# Reserved top-level paths on github.com that are NOT user / org accounts —
# `github.com/<reserved>/<x>` (e.g. `/trending/python`) must not be parsed as
# the `<owner>/<repo>` shape. GitHub forbids these as account names.
_GH_RESERVED_PATHS = frozenset(
    {
        "about",
        "account",
        "apps",
        "codespaces",
        "collections",
        "contact",
        "customer-stories",
        "dashboard",
        "enterprise",
        "explore",
        "features",
        "issues",
        "join",
        "login",
        "logout",
        "marketplace",
        "new",
        "notifications",
        "orgs",
        "pricing",
        "pulls",
        "readme",
        "search",
        "security",
        "settings",
        "sponsors",
        "stars",
        "topics",
        "trending",
        "watching",
    }
)
_REPO_PATH_RE = re.compile(r"^/([^/]+)/([^/]+?)/?$")
_ISSUE_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/issues/(\d+)/?$")
_PULL_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)/?$")
_TIMEOUT_S = 15.0
_REQUESTER = "a2web"


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
        if m.group(1).lower() in _GH_RESERVED_PATHS:
            return None
        return "repo", m.groups()
    return None


# --------------------------------------------------------------------- #
# curl_cffi transport adapter for gidgethub
# --------------------------------------------------------------------- #


class _TimeoutSentinel(gidgethub.GitHubException):
    """Internal — surfaces a transport-layer timeout from `_request`."""


class _ConnectionSentinel(gidgethub.GitHubException):
    """Internal — surfaces a transport-layer connection failure from `_request`."""


class _CurlCffiGitHubAPI(GitHubAPI):
    """gidgethub.GitHubAPI bound to a2web's `fetch_bytes` transport.

    Keeps gidgethub's auth header injection, rate-limit accounting, and
    response parsing — but routes every byte through the curl_cffi tier so
    we inherit JA3/JA4 impersonation, per-host breakers, and proxy routing.

    Transport-layer failures (timeout / connection refused / DNS) are
    surfaced as `_TimeoutSentinel` / `_ConnectionSentinel`; the handler maps
    them to closed `Verdict` values. HTTP-layer responses (any non-zero
    status) are forwarded verbatim — gidgethub interprets 403-with-zero-
    remaining as `RateLimitExceeded`, 404 as `BadRequest(404)`, etc.
    """

    async def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> tuple[int, Mapping[str, str], bytes]:
        del body  # the read-only GitHub surface used here is GET-only
        if method.upper() != "GET":
            msg = f"a2web GitHub handler is read-only; refusing {method}"
            raise gidgethub.GitHubException(msg)
        outcome = await fetch_bytes(url, headers=dict(headers), timeout_s=_TIMEOUT_S)
        if outcome.verdict is FetchVerdict.timeout:
            raise _TimeoutSentinel("transport timeout")
        if outcome.status_code == 0:
            raise _ConnectionSentinel("transport connection failure")
        return outcome.status_code, outcome.headers, outcome.body

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def _make_api(settings: AppSettings) -> _CurlCffiGitHubAPI:
    return _CurlCffiGitHubAPI(
        _REQUESTER,
        oauth_token=settings.github_token or None,
    )


# --------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------- #


class GitHubHandler:
    """Tier-0 handler for github.com repo / issue / pull URLs."""

    name: str = "site_handler:github"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _classify(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        classified = _classify(url)
        if classified is None:
            return _empty_result(url, Verdict.not_found)
        kind, parts = classified
        gh = _make_api(state.settings)

        try:
            if kind == "repo":
                return await _fetch_repo(url, parts, gh)
            if kind == "issue":
                return await _fetch_issue(url, parts, gh)
            return await _fetch_pull(url, parts, gh)
        except _TimeoutSentinel:
            return _empty_result(url, Verdict.timeout)
        except _ConnectionSentinel:
            return _empty_result(url, Verdict.connection_error)
        except gidgethub.RateLimitExceeded:
            return _empty_result(url, Verdict.rate_limited)
        except gidgethub.InvalidField:
            return _empty_result(url, Verdict.content_type_mismatch)
        except gidgethub.BadRequest as err:
            status = getattr(err, "status_code", 0)
            # `status_code` may be an HTTPStatus enum; cast to int for comparisons.
            status_int = int(status) if status else 0
            if status_int == 404:
                return _empty_result(url, Verdict.not_found)
            if status_int == 429:
                return _empty_result(url, Verdict.rate_limited)
            return _empty_result(url, Verdict.connection_error)
        except gidgethub.GitHubException:
            return _empty_result(url, Verdict.connection_error)


# --------------------------------------------------------------------- #
# Per-kind fetchers
# --------------------------------------------------------------------- #


async def _fetch_repo(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo = parts
    repo_data = await gh.getitem("/repos/{owner}/{repo}", {"owner": owner, "repo": repo})

    readme_md = ""
    try:
        readme_payload = await gh.getitem("/repos/{owner}/{repo}/readme", {"owner": owner, "repo": repo})
    except gidgethub.BadRequest:
        readme_payload = None
    if isinstance(readme_payload, dict) and readme_payload.get("encoding") == "base64":
        import base64

        try:
            readme_md = base64.b64decode(readme_payload.get("content", "")).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            readme_md = ""

    next_links = await _fetch_repo_candidates(owner, repo, gh)

    rendered = _render_repo(repo_data, readme_md)
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        next_links=next_links,
        verdict=Verdict.ok,
    )


async def _fetch_repo_candidates(owner: str, repo: str, gh: GitHubAPI) -> list[NextLink]:
    """Top 5 open issues + top 5 open PRs as `related` candidates.

    Best-effort: any error returns what we have so far rather than failing.
    GitHub's /issues endpoint returns BOTH issues and PRs — filter out items
    with `pull_request` to keep them disjoint.
    """
    out: list[NextLink] = []
    try:
        issues_data = await gh.getitem(
            "/repos/{owner}/{repo}/issues{?state,per_page,sort,direction}",
            {"owner": owner, "repo": repo, "state": "open", "per_page": "10", "sort": "comments", "direction": "desc"},
        )
    except gidgethub.GitHubException:
        issues_data = None
    issue_count = 0
    for it in issues_data if isinstance(issues_data, list) else []:
        if issue_count >= 5:
            break
        if not isinstance(it, dict) or it.get("pull_request"):
            continue
        title = (it.get("title") or "").strip()
        number = it.get("number")
        if not title or not number:
            continue
        comments = it.get("comments", 0) or 0
        out.append(
            NextLink(
                anchor=title,
                url=f"https://github.com/{owner}/{repo}/issues/{number}",
                reason=f"issue · {comments} comments",
                kind="related",
            ),
        )
        issue_count += 1

    try:
        pulls_data = await gh.getitem(
            "/repos/{owner}/{repo}/pulls{?state,per_page,sort,direction}",
            {"owner": owner, "repo": repo, "state": "open", "per_page": "5", "sort": "popularity", "direction": "desc"},
        )
    except gidgethub.GitHubException:
        pulls_data = None
    pr_count = 0
    for pr in pulls_data if isinstance(pulls_data, list) else []:
        if pr_count >= 5:
            break
        if not isinstance(pr, dict):
            continue
        title = (pr.get("title") or "").strip()
        number = pr.get("number")
        if not title or not number:
            continue
        comments = pr.get("comments", 0) or 0
        out.append(
            NextLink(
                anchor=title,
                url=f"https://github.com/{owner}/{repo}/pull/{number}",
                reason=f"PR · {comments} comments",
                kind="related",
            ),
        )
        pr_count += 1

    return out


async def _fetch_issue(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    issue_data = await gh.getitem(
        "/repos/{owner}/{repo}/issues/{number}",
        {"owner": owner, "repo": repo, "number": number},
    )
    try:
        loaded = await gh.getitem(
            "/repos/{owner}/{repo}/issues/{number}/comments",
            {"owner": owner, "repo": repo, "number": number},
        )
    except gidgethub.GitHubException:
        loaded = None
    comments: list[Any] = loaded if isinstance(loaded, list) else []

    rendered = _render_issue(issue_data, comments, kind="Issue")
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


async def _fetch_pull(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    pr_data = await gh.getitem(
        "/repos/{owner}/{repo}/pulls/{number}",
        {"owner": owner, "repo": repo, "number": number},
    )
    try:
        loaded = await gh.getitem(
            "/repos/{owner}/{repo}/pulls/{number}/reviews",
            {"owner": owner, "repo": repo, "number": number},
        )
    except gidgethub.GitHubException:
        loaded = None
    reviews: list[Any] = loaded if isinstance(loaded, list) else []

    try:
        loaded = await gh.getitem(
            "/repos/{owner}/{repo}/issues/{number}/comments",
            {"owner": owner, "repo": repo, "number": number},
        )
    except gidgethub.GitHubException:
        loaded = None
    comments: list[Any] = loaded if isinstance(loaded, list) else []

    rendered = _render_pull(pr_data, reviews, comments)
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


# --------------------------------------------------------------------- #
# Markdown rendering — preserved byte-equivalent from v0.15
# --------------------------------------------------------------------- #


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
