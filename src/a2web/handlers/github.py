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
from http_fetch import FetchVerdict, fetch_bytes

from ..hints import OperatorHint, section_unretrieved_hint
from ..models import Heading, NextLink, Verdict
from ._common import empty_result, report_rot

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

    #: Resolved per-request bound, carried from settings at construction —
    #: `_request` is a gidgethub transport hook with no `state` in scope.
    #: Declared WITHOUT a default on purpose: a fallback to the bare `_TIMEOUT_S`
    #: would be a path where an operator's `request_timeout_scale` silently does
    #: not apply. `_make_api` is the only construction site and always sets it;
    #: anything else fails loudly instead of quietly ignoring the setting.
    timeout_s: float

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
        outcome = await fetch_bytes(url, headers=dict(headers), timeout_s=self.timeout_s)
        if outcome.verdict is FetchVerdict.timeout:
            raise _TimeoutSentinel("transport timeout")
        if outcome.status_code == 0:
            raise _ConnectionSentinel("transport connection failure")
        return outcome.status_code, outcome.headers, outcome.body

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def _make_api(settings: AppSettings) -> _CurlCffiGitHubAPI:
    api = _CurlCffiGitHubAPI(
        _REQUESTER,
        oauth_token=settings.github_token or None,
    )
    api.timeout_s = settings.request_timeout(_TIMEOUT_S)
    return api


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
            return empty_result(url, Verdict.not_found)
        kind, parts = classified
        gh = _make_api(state.settings)

        try:
            if kind == "repo":
                return await _fetch_repo(url, parts, gh)
            if kind == "issue":
                return await _fetch_issue(url, parts, gh)
            return await _fetch_pull(url, parts, gh)
        except _TimeoutSentinel:
            return empty_result(url, Verdict.timeout)
        except _ConnectionSentinel:
            return empty_result(url, Verdict.connection_error)
        except gidgethub.RateLimitExceeded:
            return empty_result(url, Verdict.rate_limited)
        except gidgethub.InvalidField:
            return empty_result(url, Verdict.content_type_mismatch)
        except gidgethub.BadRequest as err:
            status = getattr(err, "status_code", 0)
            # `status_code` may be an HTTPStatus enum; cast to int for comparisons.
            status_int = int(status) if status else 0
            if status_int == 404:
                return empty_result(url, Verdict.not_found)
            if status_int == 429:
                return empty_result(url, Verdict.rate_limited)
            return empty_result(url, Verdict.connection_error)
        except gidgethub.GitHubException:
            return empty_result(url, Verdict.connection_error)


# --------------------------------------------------------------------- #
# Partial degradation — a supplementary call failed, the primary one did not
#
# Every helper below distinguishes THREE outcomes, not two: retrieved-with-rows,
# retrieved-and-genuinely-empty, and NOT retrieved. Collapsing the last two into
# `[]` is what made a rate-limited comments fetch render identically to an issue
# with no comments (ADR-0009 — a2web knew, and told the caller something that
# read as complete).
#
# `None` is the unretrieved marker; a list (including `[]`) means the call
# succeeded. Callers accumulate the section names into `unretrieved` and the
# renderers emit an explicit marker for each, so absence-because-unretrieved is
# never spelled the same way as absence-because-empty.
# --------------------------------------------------------------------- #

#: Rendered in place of a section body that could not be retrieved. Prose, not a
#: sentinel token: the primary consumer is an LLM reading `content_md`, and it
#: must not be able to mistake this for the section being empty at the source.
_UNRETRIEVED_MARKER = "_(this section was NOT retrieved — treat as unknown, not as empty)_"


async def _get_or_none(template: str, params: Mapping[str, str], *, gh: GitHubAPI) -> Any | None:
    """GET `template`, or `None` when the call failed.

    `None` means UNRETRIEVED and is never conflated with an empty result. The
    caller decides whether that is fatal — for a supplementary section it is
    not, but it is also never silent.
    """
    try:
        return await gh.getitem(template, dict(params))
    except gidgethub.GitHubException:
        return None


def _rows_or_unretrieved(loaded: Any | None, section: str, unretrieved: list[str]) -> list[Any]:
    """Normalize a `_get_or_none` result to rows, recording an unretrieved section.

    A non-list success (GitHub answering with an unexpected shape) counts as
    unretrieved too — we did not get the section, whatever the reason.
    """
    if isinstance(loaded, list):
        return loaded
    unretrieved.append(section)
    return []


def _degradation_hint(unretrieved: list[str]) -> OperatorHint | None:
    """One hint naming every unretrieved section, or `None` when all succeeded."""
    return section_unretrieved_hint(unretrieved) if unretrieved else None


# --------------------------------------------------------------------- #
# Per-kind fetchers
# --------------------------------------------------------------------- #


async def _fetch_repo(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo = parts
    unretrieved: list[str] = []
    repo_data = await gh.getitem("/repos/{owner}/{repo}", {"owner": owner, "repo": repo})

    readme_md = ""
    # Caught `BadRequest` only until 2026-07-31, where four sibling guards catch
    # `GitHubException` — so a RATE-LIMITED README (`RateLimitExceeded`) escaped
    # to the handler's outer except and aborted the entire repo fetch. The
    # opposite failure from the other five sites: over-failing where they
    # under-fail, same family, same fix.
    readme_payload = await _get_or_none("/repos/{owner}/{repo}/readme", {"owner": owner, "repo": repo}, gh=gh)
    if readme_payload is None:
        unretrieved.append("README")
    if isinstance(readme_payload, dict) and readme_payload.get("encoding") == "base64":
        import base64

        try:
            readme_md = base64.b64decode(readme_payload.get("content", "")).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            readme_md = ""
            # RETRIEVED but undecodable. `unretrieved` is untouched here by
            # design (the call succeeded), so without this the README section
            # is simply omitted and reads as "this repo has no README" — the
            # section-marking machinery below defeated by a decode failure
            # rather than by a failed fetch.
            report_rot("github", section="README", cause="base64_decode")
    elif isinstance(readme_payload, dict):
        # A 200 whose `encoding` is not `base64` — GitHub has served base64
        # here for the life of this handler, so a different value is a contract
        # change, not a repo without a README.
        report_rot("github", section="README", cause="encoding", encoding=readme_payload.get("encoding"))

    next_links = await _fetch_repo_candidates(owner, repo, gh, unretrieved)

    rendered = _render_repo(repo_data, readme_md, readme_unretrieved="README" in unretrieved)
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        next_links=next_links,
        operator_hint=_degradation_hint(unretrieved),
        verdict=Verdict.ok,
        volatility="live",
    )


async def _fetch_repo_candidates(
    owner: str,
    repo: str,
    gh: GitHubAPI,
    unretrieved: list[str],
) -> list[NextLink]:
    """Top 5 open issues + top 5 open PRs as `related` candidates.

    Best-effort in the sense that a failure never sinks the fetch — but no
    longer SILENT: a failed sub-fetch records its section in `unretrieved`, so
    the caller can say "no open issues were retrieved" rather than presenting an
    empty candidate list as "this repo has no open issues".

    GitHub's /issues endpoint returns BOTH issues and PRs — filter out items
    with `pull_request` to keep them disjoint.
    """
    out: list[NextLink] = []
    issues_data = await _get_or_none(
        "/repos/{owner}/{repo}/issues{?state,per_page,sort,direction}",
        {"owner": owner, "repo": repo, "state": "open", "per_page": "10", "sort": "comments", "direction": "desc"},
        gh=gh,
    )
    if issues_data is None:
        unretrieved.append("open issues")
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
    # Rows RETRIEVED, every one unusable. `unretrieved` stays empty because the
    # call succeeded, so this used to read as "no open issues" — a repo with a
    # hundred of them, reported as having none. Non-empty input with zero rows
    # surviving is rot; a genuinely empty list stays silent.
    if isinstance(issues_data, list) and issues_data and issue_count == 0:
        report_rot("github", section="open issues", cause="row_shape", rows=len(issues_data))

    pulls_data = await _get_or_none(
        "/repos/{owner}/{repo}/pulls{?state,per_page,sort,direction}",
        {"owner": owner, "repo": repo, "state": "open", "per_page": "5", "sort": "popularity", "direction": "desc"},
        gh=gh,
    )
    if pulls_data is None:
        unretrieved.append("open pull requests")
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
    if isinstance(pulls_data, list) and pulls_data and pr_count == 0:
        report_rot("github", section="open pull requests", cause="row_shape", rows=len(pulls_data))

    return out


async def _fetch_issue(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    unretrieved: list[str] = []
    issue_data = await gh.getitem(
        "/repos/{owner}/{repo}/issues/{number}",
        {"owner": owner, "repo": repo, "number": number},
    )
    loaded = await _get_or_none(
        "/repos/{owner}/{repo}/issues/{number}/comments",
        {"owner": owner, "repo": repo, "number": number},
        gh=gh,
    )
    comments: list[Any] = _rows_or_unretrieved(loaded, "comments", unretrieved)

    rendered = _render_issue(issue_data, comments, kind="Issue", comments_unretrieved=bool(unretrieved))
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        operator_hint=_degradation_hint(unretrieved),
        verdict=Verdict.ok,
        volatility="live",
    )


async def _fetch_pull(url: str, parts: tuple[str, ...], gh: GitHubAPI) -> TierResult:
    from ..tiers import Rendered, TierResult

    owner, repo, number = parts
    unretrieved: list[str] = []
    pr_data = await gh.getitem(
        "/repos/{owner}/{repo}/pulls/{number}",
        {"owner": owner, "repo": repo, "number": number},
    )
    loaded = await _get_or_none(
        "/repos/{owner}/{repo}/pulls/{number}/reviews",
        {"owner": owner, "repo": repo, "number": number},
        gh=gh,
    )
    reviews: list[Any] = _rows_or_unretrieved(loaded, "reviews", unretrieved)

    loaded = await _get_or_none(
        "/repos/{owner}/{repo}/issues/{number}/comments",
        {"owner": owner, "repo": repo, "number": number},
        gh=gh,
    )
    comments: list[Any] = _rows_or_unretrieved(loaded, "comments", unretrieved)

    rendered = _render_pull(
        pr_data,
        reviews,
        comments,
        reviews_unretrieved="reviews" in unretrieved,
        comments_unretrieved="comments" in unretrieved,
    )
    return TierResult(
        body=b"",
        content_type="application/json",
        status_code=200,
        final_url=url,
        pre_rendered=Rendered.from_dict(rendered),
        operator_hint=_degradation_hint(unretrieved),
        verdict=Verdict.ok,
        volatility="live",
    )


# --------------------------------------------------------------------- #
# Markdown rendering — preserved byte-equivalent from v0.15
# --------------------------------------------------------------------- #


def _render_repo(data: dict, readme_md: str, *, readme_unretrieved: bool = False) -> dict[str, object]:
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
    elif readme_unretrieved:
        # A repo with no README and a repo whose README we could not fetch are
        # different facts. Only the first justifies silence.
        parts.append("\n---\n\n## README\n\n")
        parts.append(_UNRETRIEVED_MARKER + "\n")

    headings: list[Heading] = [Heading(level=1, text=full_name)]
    if readme_md or readme_unretrieved:
        headings.append(Heading(level=2, text="README"))

    return {
        "content_md": "".join(parts).strip() + "\n",
        "title": full_name,
        "byline": data.get("owner", {}).get("login") if isinstance(data.get("owner"), dict) else None,
        "headings": headings,
    }


def _render_issue(
    data: dict,
    comments: list,
    *,
    kind: str,
    comments_unretrieved: bool = False,
) -> dict[str, object]:
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
    if comments_unretrieved:
        # Without this line an empty `## Comments` section reads as "this issue
        # has no comments" — which is exactly what a throttled sub-fetch used to
        # look like.
        parts.append(_UNRETRIEVED_MARKER + "\n\n")
    rendered_comments = 0
    for c in comments:
        if not isinstance(c, dict):
            continue
        c_user = ""
        if isinstance(c_user_obj := c.get("user"), dict):
            c_user = c_user_obj.get("login") or ""
        c_body = c.get("body") or ""
        if c_body:
            parts.append(f"**{c_user}:**\n\n{c_body}\n\n")
            rendered_comments += 1
    # The `comments_unretrieved` marker above guards a FAILED fetch. This guards
    # the other route to the same empty section: comments retrieved, `body`
    # rotted, nothing rendered, no marker — the failure `:550` exists to prevent,
    # reached from inside a successful payload.
    if comments and not comments_unretrieved and rendered_comments == 0:
        report_rot("github", section="comments", cause="row_shape", rows=len(comments))

    return {
        "content_md": "".join(parts).strip() + "\n",
        "title": f"{kind} #{number}: {title}",
        "byline": user_login or None,
        "headings": [Heading(level=1, text=f"{kind} #{number}: {title}"), Heading(level=2, text="Comments")],
    }


def _render_pull(
    data: dict,
    reviews: list,
    comments: list,
    *,
    reviews_unretrieved: bool = False,
    comments_unretrieved: bool = False,
) -> dict[str, object]:
    rendered = _render_issue(data, comments, kind="Pull", comments_unretrieved=comments_unretrieved)
    if not reviews and not reviews_unretrieved:
        return rendered
    if reviews_unretrieved:
        base = [str(rendered["content_md"]), "\n## Reviews\n\n", _UNRETRIEVED_MARKER + "\n"]
        headings = rendered["headings"]
        return {
            **rendered,
            "content_md": "".join(base).strip() + "\n",
            "headings": [*headings, Heading(level=2, text="Reviews")] if isinstance(headings, list) else headings,
        }

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
