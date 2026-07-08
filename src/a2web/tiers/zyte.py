"""Zyte API tier — paid last-resort fetch (reddit-reachability-never-silent-miss).

Single POST against `https://api.zyte.com/v1/extract`. Two modes:

- **`browserHtml`** (default): Zyte renders the page + solves anti-bot
  challenges server-side and returns rendered HTML. The right mode for
  JS-dependent targets. The returned HTML is converted to markdown via the
  boundary-safe `html_fragment` package and wrapped as `pre_rendered` so the
  orchestrator installs it directly.
- **`httpResponseBody`** (raw): Zyte proxies the origin response and returns
  the base64-encoded body without browser rendering — cheaper, and sufficient
  for **server-rendered** targets (e.g. old.reddit `?limit=500`). The decoded
  bytes + origin content-type are returned; the caller owns extraction (the
  Reddit handler parses old.reddit's flat HTML itself). Selected per-dispatch
  via the `mode` kwarg (`reddit-via-zyte` design §2).

Env-gated: registered only when `settings.zyte_key` is set (the manifest returns
`Unavailable` otherwise). Dispatched out-of-band by the planner ONLY after the
free/proxied ladder is exhausted on a wall verdict, OR eagerly by the Reddit
handler on a known-walled host — paid egress is a cost-incurring path, never
speculative on the generic ladder.

Auth/billing failure (401/402/403) maps to `Verdict.paid_auth_error` in BOTH
modes. The orchestrator treats that as an authoritative hard-stop (bad key /
exhausted billing must surface loudly), never a silent downgrade.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx

from ..models import Verdict
from ..packages.html_fragment import to_markdown
from ._paid import paid_verdict_for_status

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_API_URL = "https://api.zyte.com/v1/extract"
# Zyte renders server-side (browserHtml) — allow generous headroom. Heavy pages
# like a Reddit listing take ~8-40s solo and can exceed 40s under concurrent
# load, timing out into a weaker fallback; 60s covers the slow tail while
# staying bounded (the caller's overall ladder is still finite).
_TIMEOUT_S = 60.0

# The two supported fetch modes. `browserHtml` renders; `httpResponseBody`
# proxies the raw origin response (cheap, no browser) for server-rendered pages.
ZyteMode = str  # "browserHtml" | "httpResponseBody"


def _zyte_extract_request(url: str, *, raw: bool, scroll: bool, scroll_cap: int) -> dict[str, Any]:
    """Build the Zyte `/extract` request body.

    `raw` (httpResponseBody) proxies the origin — no browser, no actions.
    `browserHtml` renders; when `scroll` is set (listing-completeness Slice 2),
    a bounded `scrollBottom` + `waitForTimeout` action sequence is appended so
    the server-side render materialises lazy-loaded / infinite-scroll items
    before snapshotting. Pure — the httpx POST lives in `fetch`.
    """
    if raw:
        return {"url": url, "httpResponseBody": True}
    request: dict[str, Any] = {"url": url, "browserHtml": True}
    if scroll and scroll_cap > 0:
        request["actions"] = [
            step for _ in range(scroll_cap) for step in ({"action": "scrollBottom"}, {"action": "waitForTimeout", "timeout": 2})
        ]
    return request


class ZyteTier:
    """Zyte extract as a paid tier — rendered (`browserHtml`) or raw (`httpResponseBody`)."""

    name: str = "zyte"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        mode: ZyteMode = "browserHtml",
        scroll: bool = False,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Zyte owns egress + challenge solving.
        from . import Rendered, TierResult  # local import — avoid circular at module load

        key = state.settings.zyte_key
        if not key:
            # Defensive: the manifest gates registration on the key, so this
            # path is unreachable in production. Skip silently rather than error.
            return TierResult(body=b"", content_type="text/html", status_code=0, final_url=url, skipped=True, verdict=Verdict.other)

        raw = mode == "httpResponseBody"
        request = _zyte_extract_request(url, raw=raw, scroll=scroll, scroll_cap=state.settings.listing_scroll_cap)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
                resp = await client.post(_API_URL, json=request, auth=(key, ""))
        except httpx.TimeoutException:
            return TierResult(body=b"", content_type="text/html", status_code=0, final_url=url, verdict=Verdict.timeout)
        except httpx.HTTPError:
            return TierResult(body=b"", content_type="text/html", status_code=0, final_url=url, verdict=Verdict.connection_error)

        verdict = paid_verdict_for_status(resp.status_code)
        if verdict is not Verdict.ok:
            return TierResult(body=b"", content_type="text/html", status_code=resp.status_code, final_url=url, verdict=verdict)

        payload = resp.json()
        final_url = payload.get("url") or url

        if raw:
            # `httpResponseBody` — the caller (Reddit handler) parses the body
            # itself, so no markdown conversion here. Hand back decoded origin
            # bytes + content-type. Verdict is `ok` when a body is present,
            # `length_floor` when the origin returned an empty 200.
            encoded = payload.get("httpResponseBody") or ""
            body = base64.b64decode(encoded) if encoded else b""
            content_type = _content_type_from_headers(payload.get("httpResponseHeaders")) or "text/html"
            return TierResult(
                body=body,
                content_type=content_type,
                status_code=resp.status_code,
                final_url=final_url,
                verdict=Verdict.ok if body else Verdict.length_floor,
            )

        # `browserHtml` — render to markdown and install as pre_rendered.
        html = payload.get("browserHtml") or ""
        markdown = to_markdown(html, base_url=final_url).strip() if html else ""
        pre_rendered = Rendered(content_md=markdown) if markdown else None
        return TierResult(
            body=html.encode("utf-8"),
            content_type="text/html",
            status_code=resp.status_code,
            final_url=final_url,
            pre_rendered=pre_rendered,
            verdict=Verdict.ok if pre_rendered is not None else Verdict.length_floor,
        )


def _content_type_from_headers(headers: Any) -> str | None:
    """Extract `content-type` from Zyte's `httpResponseHeaders` list.

    Zyte returns headers as `[{"name": ..., "value": ...}, ...]`. Returns the
    first content-type value (case-insensitive name match), or None.
    """
    if not isinstance(headers, list):
        return None
    for header in headers:
        if isinstance(header, dict) and str(header.get("name", "")).lower() == "content-type":
            value = header.get("value")
            if value:
                return str(value)
    return None
