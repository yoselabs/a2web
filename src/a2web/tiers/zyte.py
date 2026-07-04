"""Zyte API tier — paid last-resort fetch (reddit-reachability-never-silent-miss).

Single POST against `https://api.zyte.com/v1/extract` requesting `browserHtml`
(Zyte renders + solves anti-bot challenges server-side). The returned HTML is
converted to markdown via the boundary-safe `html_fragment` package and wrapped
as `pre_rendered` so the orchestrator installs it directly.

Env-gated: registered only when `settings.zyte_key` is set (the manifest returns
`Unavailable` otherwise). Dispatched out-of-band by the planner ONLY after the
free/proxied ladder is exhausted on a wall verdict — paid egress is a cost-
incurring last resort, never speculative.

Auth/billing failure (401/402/403) maps to `Verdict.paid_auth_error`. The
orchestrator treats that as an authoritative hard-stop (bad key / exhausted
billing must surface loudly), never a silent downgrade to a cheaper tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ..models import Verdict
from ..packages.html_fragment import to_markdown
from ._paid import paid_verdict_for_status

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_API_URL = "https://api.zyte.com/v1/extract"
_TIMEOUT_S = 40.0  # Zyte renders server-side — allow generous headroom.


class ZyteTier:
    """Zyte browserHtml extract as a paid, out-of-band last resort."""

    name: str = "zyte"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Zyte owns egress + challenge solving.
        from . import Rendered, TierResult  # local import — avoid circular at module load

        key = state.settings.zyte_key
        if not key:
            # Defensive: the manifest gates registration on the key, so this
            # path is unreachable in production. Skip silently rather than error.
            return TierResult(
                body=b"", content_type="text/html", status_code=0, final_url=url, skipped=True, verdict=Verdict.other
            )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
                resp = await client.post(_API_URL, json={"url": url, "browserHtml": True}, auth=(key, ""))
        except httpx.TimeoutException:
            return TierResult(body=b"", content_type="text/html", status_code=0, final_url=url, verdict=Verdict.timeout)
        except httpx.HTTPError:
            return TierResult(
                body=b"", content_type="text/html", status_code=0, final_url=url, verdict=Verdict.connection_error
            )

        verdict = paid_verdict_for_status(resp.status_code)
        if verdict is not Verdict.ok:
            return TierResult(
                body=b"", content_type="text/html", status_code=resp.status_code, final_url=url, verdict=verdict
            )

        payload = resp.json()
        html = payload.get("browserHtml") or ""
        final_url = payload.get("url") or url
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
