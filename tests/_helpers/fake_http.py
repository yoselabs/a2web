"""Shared fake `curl_cffi.AsyncSession` for handler and tier tests.

After the `http_fetch` primitive migration, every project HTTP call goes
through `curl_cffi.requests.AsyncSession`. These helpers patch the session
factory at the primitive's import path so tests can intercept fetches with
a router callable (`(self, url, **kwargs) -> FakeCurlResp`).
"""

from __future__ import annotations

from typing import Any

import pytest


class FakeCurlResp:
    """Duck-typed stand-in for curl_cffi's `Response` — exposes only the
    attributes the primitive reads: `status_code`, `content`, `headers`,
    `url`. Mirrors `httpx.Response`'s ergonomics with `text=` / `body=`."""

    def __init__(
        self,
        status_code: int = 200,
        *,
        text: str = "",
        body: bytes | None = None,
        json: Any = None,
        content_type: str = "application/json",
        url: str = "https://example.com/",
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        import json as _json

        self.status_code = status_code
        if json is not None:
            self.content = _json.dumps(json).encode("utf-8")
        elif body is not None:
            self.content = body
        else:
            self.content = text.encode("utf-8")
        self.url = url
        # If `headers` is given, it fully replaces the default content-type one.
        # `extra_headers` augments either.
        self.headers: dict[str, str] = dict(headers) if headers else {"content-type": content_type}
        if extra_headers:
            self.headers.update(extra_headers)


class FakeCurlSession:
    """Async-context-manager fake for `curl_cffi.requests.AsyncSession`.

    Stores the per-call kwargs on `last_request` so tests can assert on
    forwarded headers / params / proxies / cookies.
    """

    def __init__(self, responder: Any) -> None:
        self._responder = responder
        self.last_request: dict[str, Any] = {}
        self.session_kwargs: dict[str, Any] = {}

    async def __aenter__(self) -> FakeCurlSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> FakeCurlResp:
        self.last_request = {"url": url, **kwargs}
        result = self._responder(self, url, **kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return result


def patch_curl_session(monkeypatch: pytest.MonkeyPatch, responder: Any) -> FakeCurlSession:
    """Replace `cr.AsyncSession` at the primitive's import site with a fake.

    `responder(self, url, **kwargs) -> FakeCurlResp` may be sync or async.
    Returns the FakeCurlSession instance so tests can inspect `last_request`.
    """
    fake = FakeCurlSession(responder)

    def _factory(**kw: Any) -> FakeCurlSession:
        fake.session_kwargs = kw
        return fake

    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", _factory)
    return fake
