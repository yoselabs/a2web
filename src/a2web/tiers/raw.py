"""Raw tier — curl_cffi with Chrome JA3/JA4 TLS impersonation.

Maps HTTP outcomes to closed-enum verdicts. Honors per-host purgatory
breakers from `state.breakers`. Conditional GET (etag + last-modified) is
handled by the orchestrator via `state.sqlite`; the tier passes the
relevant headers when present in `kwargs`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from curl_cffi import requests as curl_requests
from curl_cffi.requests import exceptions as curl_exceptions

from ..models import Verdict
from ..settings import AppSettings

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_DEFAULT_TIMEOUT_S = 10
_IMPERSONATE = "chrome120"


def _verdict_for_status(status: int, content_type: str) -> Verdict:
    if status == 404:
        return Verdict.not_found
    if status == 429:
        return Verdict.rate_limited
    if status >= 500:
        return Verdict.connection_error
    if status >= 400:
        return Verdict.connection_error
    if "html" not in content_type.lower():
        return Verdict.content_type_mismatch
    return Verdict.ok


def _is_proxy_error(exc: BaseException) -> bool:
    """Heuristic: curl_cffi surfaces proxy failures via generic RequestException.

    The error message contains "proxy" or "SOCKS" in practice; lacking a
    typed exception we string-match. Conservative: false negatives just
    yield connection_error (current behavior); never confuses non-proxy
    failures with proxy failures.
    """
    msg = str(exc).lower()
    return "proxy" in msg or "socks" in msg or "tunnel" in msg


def _conditional_headers(extras: dict[str, Any]) -> dict[str, str]:
    """Build conditional-GET headers from an optional cached row."""
    headers: dict[str, str] = {}
    etag = extras.get("etag")
    if isinstance(etag, str) and etag:
        headers["If-None-Match"] = etag
    last_modified = extras.get("last_modified")
    if isinstance(last_modified, str) and last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


class RawTier:
    """Default tier for any URL — curl_cffi with TLS impersonation."""

    name: str = "raw"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        conditional_extras: dict[str, Any] | None = None,
        proxy_url: str | None = None,
        cookies: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del kwargs  # accept-and-ignore for protocol-uniform dispatch
        from . import TierResult

        settings: AppSettings = state.settings
        request_headers = {"User-Agent": settings.default_ua}
        if conditional_extras:
            request_headers.update(_conditional_headers(conditional_extras))

        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        breaker = await state.breakers.get_breaker(host) if state.breakers is not None and host else None

        async def _do_request() -> TierResult:
            session_kwargs: dict[str, Any] = {"impersonate": _IMPERSONATE}
            request_kwargs: dict[str, Any] = {
                "headers": request_headers,
                "timeout": _DEFAULT_TIMEOUT_S,
                "allow_redirects": True,
            }
            if proxy_url:
                request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
            if cookies:
                request_kwargs["cookies"] = dict(cookies)
            async with curl_requests.AsyncSession(**session_kwargs) as session:
                try:
                    response = await session.get(url, **request_kwargs)
                except curl_exceptions.Timeout:
                    return TierResult(
                        body=b"",
                        content_type="",
                        status_code=0,
                        final_url=url,
                        verdict=Verdict.timeout,
                    )
                except curl_exceptions.RequestException as exc:
                    if proxy_url and _is_proxy_error(exc):
                        return TierResult(
                            body=b"",
                            content_type="",
                            status_code=0,
                            final_url=url,
                            verdict=Verdict.proxy_unavailable,
                        )
                    return TierResult(
                        body=b"",
                        content_type="",
                        status_code=0,
                        final_url=url,
                        verdict=Verdict.connection_error,
                    )

            content_type = response.headers.get("content-type", "")
            response_headers = dict(response.headers)

            # 304 Not Modified — caller will reuse cached body
            if response.status_code == 304:
                return TierResult(
                    body=b"",
                    content_type=content_type,
                    status_code=304,
                    final_url=str(response.url),
                    headers=response_headers,
                    conditional_hit=True,
                    verdict=Verdict.ok,
                )

            return TierResult(
                body=response.content,
                content_type=content_type,
                status_code=response.status_code,
                final_url=str(response.url),
                headers=response_headers,
                verdict=_verdict_for_status(response.status_code, content_type),
            )

        if breaker is None:
            return await _do_request()

        try:
            async with breaker:
                return await _do_request()
        except Exception:
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=url,
                verdict=Verdict.connection_error,
            )
