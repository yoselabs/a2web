"""Jina r.jina.ai tier — markdown-as-a-service fallback after raw.

Single GET against `https://r.jina.ai/<url>` returning markdown. Bearer
auth optional; free tier works without. Result is wrapped as
`pre_rendered` so the orchestrator skips trafilatura.

Hosts on `settings.jina_deny_hosts` short-circuit before any HTTP call —
Jina sees the URL, so anything credential-bearing or intranet should
opt out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_BASE_URL = "https://r.jina.ai/"
_TIMEOUT_S = 15.0


def _is_denied(url: str, deny_hosts: list[str]) -> bool:
    if not deny_hosts:
        return False
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h.lower() or host.endswith("." + h.lower()) for h in deny_hosts)


def _verdict_for_status(status: int) -> Verdict:
    if status == 429:
        return Verdict.rate_limited
    if status == 404:
        return Verdict.not_found
    if status >= 500:
        return Verdict.connection_error
    if status >= 400:
        return Verdict.connection_error
    return Verdict.ok


class JinaTier:
    """r.jina.ai reader as a post-raw fallback."""

    name: str = "jina"

    async def fetch(self, url: str, *, state: AppState, proxy_url: str | None = None) -> TierResult:
        from . import TierResult  # local import — avoid circular at module load

        if _is_denied(url, state.settings.jina_deny_hosts):
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=0,
                final_url=url,
                tier_extras={"skipped": True, "reason": "deny-list"},
                verdict=Verdict.other,
            )

        headers = {"X-Return-Format": "markdown", "Accept": "text/markdown"}
        if state.settings.jina_key:
            headers["Authorization"] = f"Bearer {state.settings.jina_key}"

        target = _BASE_URL + url
        try:
            client = (
                httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True, proxy=proxy_url)
                if proxy_url
                else httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True)
            )
            async with client:
                resp = await client.get(target, headers=headers)
        except httpx.ProxyError:
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=0,
                final_url=url,
                tier_extras={"proxy_url": proxy_url} if proxy_url else {},
                verdict=Verdict.proxy_unavailable,
            )
        except httpx.TimeoutException:
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=0,
                final_url=url,
                verdict=Verdict.timeout,
            )
        except httpx.HTTPError:
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=0,
                final_url=url,
                verdict=Verdict.connection_error,
            )

        verdict = _verdict_for_status(resp.status_code)
        markdown = resp.text if verdict == Verdict.ok else ""
        extras: dict[str, object] = {}
        if verdict == Verdict.ok and markdown:
            extras["pre_rendered"] = {
                "content_md": markdown,
                "title": None,
                "byline": None,
                "headings": [],
            }
        return TierResult(
            body=markdown.encode("utf-8"),
            content_type="text/markdown",
            status_code=resp.status_code,
            final_url=str(resp.url) or url,
            headers={k.lower(): v for k, v in resp.headers.items()},
            tier_extras=extras,
            verdict=verdict,
        )
