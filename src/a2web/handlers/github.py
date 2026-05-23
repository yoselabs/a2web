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
import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

from ..models import Heading, NextLink, Verdict
from ..packages.http_fetch import FetchOutcome, FetchVerdict, fetch_bytes

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
        "about", "account", "apps", "codespaces", "collections", "contact",
        "customer-stories", "dashboard", "enterprise", "explore", "features",
        "issues", "join", "login", "logout", "marketplace", "new",
        "notifications", "orgs", "pricing", "pulls", "readme", "search",
        "security", "settings", "sponsors", "stars", "topics", "trending",
        "watching",
    }
)
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
        # Skip reserved top-level paths that aren't user/org accounts.
        if m.group(1).lower() in _GH_RESERVED_PATHS:
            return None
        return "repo", m.groups()
    return None


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

        headers = {
            "User-Agent": state.settings.default_ua,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = state.settings.github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        if kind == "repo":
            return await _fetch_repo(url, parts, headers)
        if kind == "issue":
            return await _fetch_issue(url, parts, headers)
        return await _fetch_pull(url, parts, headers)


async def _get_json(url: str, headers: dict[str, str], params: dict[str, str] | None = None) -> FetchOutcome:
    """One shared GET helper for the GitHub sub-fetchers — encodes params,
    calls the primitive, returns the raw FetchOutcome (caller maps to verdict)."""
    full_url = f"{url}?{urlencode(params)}" if params else url
    return await fetch_bytes(full_url, headers=headers, timeout_s=_TIMEOUT_S)


async def _fetch_repo(url: str, parts: tuple[str, ...], headers: dict[str, str]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo = parts
    repo_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}", headers)
    if (verdict := _http_verdict(repo_outcome)) is not None:
        return _empty_result(url, verdict)
    try:
        repo_data = json.loads(repo_outcome.body)
    except (ValueError, json.JSONDecodeError):
        return _empty_result(url, Verdict.content_type_mismatch)

    readme_md = ""
    readme_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/readme", headers)
    if readme_outcome.status_code == 200:
        try:
            readme_payload = json.loads(readme_outcome.body)
        except (ValueError, json.JSONDecodeError):
            readme_payload = None
        if isinstance(readme_payload, dict) and readme_payload.get("encoding") == "base64":
            try:
                readme_md = base64.b64decode(readme_payload.get("content", "")).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                readme_md = ""

    # v0.7 link-discovery: top 5 open issues + top 5 open PRs as `related` candidates.
    # Best-effort: API errors here MUST NOT fail the whole fetch.
    next_links = await _fetch_repo_candidates(owner, repo, headers)

    rendered = _render_repo(repo_data, readme_md)
    return TierResult(
        body=repo_outcome.body,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=repo_outcome.headers,
        pre_rendered=Rendered.from_dict(rendered),
        next_links=next_links,
        verdict=Verdict.ok,
    )


async def _fetch_repo_candidates(
    owner: str,
    repo: str,
    headers: dict[str, str],
) -> list[NextLink]:
    """Fetch top 5 open issues + top 5 open PRs, return as NextLink candidates.

    Best-effort: errors on either call return what we have so far rather than
    failing the parent repo fetch. GitHub's /pulls endpoint returns PRs; the
    /issues endpoint returns BOTH issues and PRs unless filtered — we filter
    out items with `pull_request` to keep them disjoint.
    """
    out: list[NextLink] = []
    issues_outcome = await _get_json(
        f"{_API_BASE}/repos/{owner}/{repo}/issues",
        headers,
        params={"state": "open", "per_page": "10", "sort": "comments", "direction": "desc"},
    )
    if issues_outcome.status_code == 200:
        try:
            issues_data = json.loads(issues_outcome.body)
        except (ValueError, json.JSONDecodeError):
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

    pulls_outcome = await _get_json(
        f"{_API_BASE}/repos/{owner}/{repo}/pulls",
        headers,
        params={"state": "open", "per_page": "5", "sort": "popularity", "direction": "desc"},
    )
    if pulls_outcome.status_code == 200:
        try:
            pulls_data = json.loads(pulls_outcome.body)
        except (ValueError, json.JSONDecodeError):
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


async def _fetch_issue(url: str, parts: tuple[str, ...], headers: dict[str, str]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    issue_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}", headers)
    if (verdict := _http_verdict(issue_outcome)) is not None:
        return _empty_result(url, verdict)
    try:
        issue_data = json.loads(issue_outcome.body)
    except (ValueError, json.JSONDecodeError):
        return _empty_result(url, Verdict.content_type_mismatch)

    comments: list[Any] = []
    comments_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}/comments", headers)
    if comments_outcome.status_code == 200:
        try:
            loaded = json.loads(comments_outcome.body)
        except (ValueError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, list):
            comments = loaded

    rendered = _render_issue(issue_data, comments, kind="Issue")
    return TierResult(
        body=issue_outcome.body,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=issue_outcome.headers,
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


async def _fetch_pull(url: str, parts: tuple[str, ...], headers: dict[str, str]) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    pr_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/pulls/{number}", headers)
    if (verdict := _http_verdict(pr_outcome)) is not None:
        return _empty_result(url, verdict)
    try:
        pr_data = json.loads(pr_outcome.body)
    except (ValueError, json.JSONDecodeError):
        return _empty_result(url, Verdict.content_type_mismatch)

    reviews: list[Any] = []
    reviews_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/pulls/{number}/reviews", headers)
    if reviews_outcome.status_code == 200:
        try:
            loaded = json.loads(reviews_outcome.body)
        except (ValueError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, list):
            reviews = loaded

    comments: list[Any] = []
    comments_outcome = await _get_json(f"{_API_BASE}/repos/{owner}/{repo}/issues/{number}/comments", headers)
    if comments_outcome.status_code == 200:
        try:
            loaded = json.loads(comments_outcome.body)
        except (ValueError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, list):
            comments = loaded

    rendered = _render_pull(pr_data, reviews, comments)
    return TierResult(
        body=pr_outcome.body,
        content_type="application/json",
        status_code=200,
        final_url=url,
        headers=pr_outcome.headers,
        pre_rendered=Rendered.from_dict(rendered),
        verdict=Verdict.ok,
    )


def _http_verdict(outcome: FetchOutcome) -> Verdict | None:
    """Map a non-success `FetchOutcome` to a closed verdict; return None on 200."""
    if outcome.verdict is FetchVerdict.timeout:
        return Verdict.timeout
    if outcome.status_code == 200 and outcome.verdict is FetchVerdict.ok:
        return None
    if outcome.status_code == 404 or outcome.verdict is FetchVerdict.not_found:
        return Verdict.not_found
    if outcome.status_code == 429 or outcome.verdict is FetchVerdict.rate_limited:
        return Verdict.rate_limited
    if outcome.status_code == 403 and outcome.headers.get("x-ratelimit-remaining") == "0":
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
