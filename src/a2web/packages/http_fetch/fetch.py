"""http_fetch — the shared HTTP transport primitive.

Used by `RawTier`, `ArchiveTier`, and every site handler. Provides
`curl_cffi.AsyncSession` with Chrome JA3/JA4 TLS impersonation, proxy
routing, per-host circuit-breaker integration, and closed-verdict error
mapping. The primitive never raises on routine HTTP failures — every
outcome maps to a `FetchVerdict` on the returned `FetchOutcome`.

This module MUST NOT import from `a2web.<domain>`. Domain `Verdict`
translation lives at the tier / handler boundary, where the same string
values map across by name.
"""

from __future__ import annotations

from typing import Any

from curl_cffi import requests as cr
from curl_cffi.requests import exceptions as ce

from .models import FetchOutcome, FetchVerdict

# Project default Chrome TLS impersonation profile — kept in sync with the
# value `RawTier` previously hard-coded.
_IMPERSONATE = "chrome120"
_DEFAULT_TIMEOUT_S = 10.0


def _conditional_headers(extras: dict[str, str] | None) -> dict[str, str]:
    """Translate cached `etag` / `last_modified` extras into conditional-GET
    request headers. Robust to missing / blank / non-string values."""
    if not extras:
        return {}
    out: dict[str, str] = {}
    etag = extras.get("etag")
    if isinstance(etag, str) and etag:
        out["If-None-Match"] = etag
    last_modified = extras.get("last_modified")
    if isinstance(last_modified, str) and last_modified:
        out["If-Modified-Since"] = last_modified
    return out


def _is_proxy_error(exc: BaseException) -> bool:
    """Heuristic — curl_cffi surfaces proxy failures via generic
    `RequestException`; the message contains "proxy" / "socks" / "tunnel"."""
    msg = str(exc).lower()
    return "proxy" in msg or "socks" in msg or "tunnel" in msg


def _status_to_verdict(status: int) -> FetchVerdict:
    """Map a non-304 HTTP status code to a closed transport verdict."""
    if status == 404:
        return FetchVerdict.not_found
    if status == 429:
        return FetchVerdict.rate_limited
    if status >= 400:
        return FetchVerdict.connection_error
    return FetchVerdict.ok


def _failure(url: str, verdict: FetchVerdict) -> FetchOutcome:
    return FetchOutcome(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        headers={},
        verdict=verdict,
    )


async def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    proxy_url: str | None = None,
    cookies: dict[str, str] | None = None,
    conditional_extras: dict[str, str] | None = None,
    breaker: Any = None,
) -> FetchOutcome:
    """Issue one HTTP GET via curl_cffi with Chrome TLS impersonation.

    Returns a `FetchOutcome` with a closed `FetchVerdict`; never raises on
    routine failures (timeout, connection error, proxy error, non-2xx). On
    a 304 response paired with `conditional_extras`, returns
    `conditional_hit=True` with an empty body — the caller reuses its
    cached body.

    Cookie values and `Authorization` header values MUST NOT appear in any
    diagnostic output produced by this module.
    """
    request_headers: dict[str, str] = dict(headers or {})
    request_headers.update(_conditional_headers(conditional_extras))

    async def _do() -> FetchOutcome:
        session_kwargs: dict[str, Any] = {"impersonate": _IMPERSONATE}
        request_kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout_s,
            "allow_redirects": True,
        }
        if proxy_url:
            request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
        if cookies:
            request_kwargs["cookies"] = dict(cookies)
        async with cr.AsyncSession(**session_kwargs) as session:
            try:
                response = await session.get(url, **request_kwargs)
            except ce.Timeout:
                return _failure(url, FetchVerdict.timeout)
            except ce.RequestException as exc:
                if proxy_url and _is_proxy_error(exc):
                    return _failure(url, FetchVerdict.proxy_unavailable)
                return _failure(url, FetchVerdict.connection_error)

        content_type = response.headers.get("content-type", "")
        response_headers = dict(response.headers)
        if response.status_code == 304:
            return FetchOutcome(
                body=b"",
                content_type=content_type,
                status_code=304,
                final_url=str(response.url),
                headers=response_headers,
                verdict=FetchVerdict.ok,
                conditional_hit=True,
            )
        return FetchOutcome(
            body=response.content,
            content_type=content_type,
            status_code=response.status_code,
            final_url=str(response.url),
            headers=response_headers,
            verdict=_status_to_verdict(response.status_code),
        )

    if breaker is None:
        return await _do()

    try:
        async with breaker:
            return await _do()
    except Exception:
        return _failure(url, FetchVerdict.connection_error)
