"""Jina r.jina.ai tier — markdown-as-a-service fallback after raw.

Single GET against `https://r.jina.ai/<url>` returning markdown. Bearer
auth optional; free tier works without. Result is wrapped as
`pre_rendered` so the orchestrator skips trafilatura.

Hosts on `settings.jina_deny_hosts` short-circuit before any HTTP call —
Jina sees the URL, so anything credential-bearing or intranet should
opt out.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_BASE_URL = "https://r.jina.ai/"
_TIMEOUT_S = 15.0

# jina wraps an upstream error as its OWN HTTP 200 with a body stub of the shape
# `Target URL returned error <status>: <reason>`. Decode the real upstream status
# generically (any 3-digit code — enumerate-by-status is what let a fixed 40[13]
# miss 404 once), behind a body-length ceiling so a long article that merely
# QUOTES the stub string is never misread as a wrapper. Tier-truthfulness
# contract: a retrieved error page surfaces its real upstream status, never `ok`.
_UPSTREAM_ERROR_RE = re.compile(r"Target URL returned error (\d{3})")
_STUB_MAX_BODY: int = 2_048


def _unwrapped_verdict(upstream_status: int) -> Verdict:
    """Map a jina-decoded UPSTREAM status to a domain Verdict.

    401/403 → `paywall` (preserves the archive-on-paywall escalation routing that
    the gate special-case used to provide); everything else routes through the
    tier's own `_verdict_for_status`. A wrapped 404 therefore surfaces as
    `not_found`, no longer masked as a length_floor wall.
    """
    if upstream_status in (401, 403):
        return Verdict.paywall
    return _verdict_for_status(upstream_status)


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

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del conditional_extras, kwargs  # Jina doesn't use conditional GET — always fresh fetch.
        from . import TierResult  # local import — avoid circular at module load

        if _is_denied(url, state.settings.jina_deny_hosts):
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=0,
                final_url=url,
                skipped=True,
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
        status_code = resp.status_code
        from . import Rendered  # local — avoid circular

        # Tier-truthfulness: a jina 200 whose body is a wrapper stub is an
        # UPSTREAM error, not real content. Decode the real status, surface it,
        # and drop the stub body so the tier never falsely wins the loop. Guarded
        # by the body-length ceiling (a long article quoting the stub is safe).
        if verdict == Verdict.ok and len(markdown) < _STUB_MAX_BODY:
            stub = _UPSTREAM_ERROR_RE.search(markdown)
            if stub is not None:
                upstream_status = int(stub.group(1))
                verdict = _unwrapped_verdict(upstream_status)
                status_code = upstream_status
                markdown = ""

        pre_rendered = Rendered(content_md=markdown) if (verdict == Verdict.ok and markdown) else None
        # `final_url` is the TARGET we were asked to read, never the r.jina.ai
        # proxy wrapper. `resp.url` is always `https://r.jina.ai/<url>` (jina
        # serves markdown at its own URL and never redirects to the origin), so
        # surfacing it would (a) leak the wrapper as the response `url` deviation
        # and (b) misdirect any downstream browser escalation onto r.jina.ai
        # instead of the real page. The origin's own redirects are invisible to
        # us through jina, so the requested `url` is the truthful final URL.
        return TierResult(
            body=markdown.encode("utf-8"),
            content_type="text/markdown",
            status_code=status_code,
            final_url=url,
            headers={k.lower(): v for k, v in resp.headers.items()},
            pre_rendered=pre_rendered,
            verdict=verdict,
        )
