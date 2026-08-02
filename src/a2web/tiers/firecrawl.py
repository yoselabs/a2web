"""Firecrawl API tier — paid last-resort fetch (reddit-reachability-never-silent-miss).

Single POST against `https://api.firecrawl.dev/v1/scrape` requesting the
`markdown` format (Firecrawl renders + extracts server-side). The returned
markdown is wrapped as `pre_rendered` so the orchestrator installs it directly.

Env-gated: registered only when `settings.firecrawl_key` is set (the manifest
returns `Unavailable` otherwise). Dispatched out-of-band by the planner ONLY
after the free/proxied ladder is exhausted on a wall verdict — paid egress is a
cost-incurring last resort, never speculative.

Auth/billing failure (401/402/403) maps to `Verdict.paid_auth_error`. The
orchestrator treats that as an authoritative hard-stop (bad key / exhausted
billing must surface loudly), never a silent downgrade to a cheaper tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ..models import Verdict
from ._paid import paid_api_breaker, paid_verdict_for_status

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_API_URL = "https://api.firecrawl.dev/v1/scrape"
_API_HOST = "api.firecrawl.dev"
# Firecrawl renders server-side, like Zyte. This was 40.0 with the comment
# "allow generous headroom" — the SAME value and the SAME claim Zyte carried
# until `2bf60ca` measured it failing: heavy pages take ~8-40s solo and exceed
# 40s under concurrent load, timing out into a weaker fallback. Zyte was raised
# to 60; firecrawl kept 40 and kept the comment the measurement had falsified.
#
# A bound present in some copies and absent in others is the dangerous variant
# of duplication — the missing one is invisible next to a sibling that has it.
# Corrected to match, since the finding is about server-side rendering under
# load and nothing about it is Zyte-specific.
_TIMEOUT_S = 60.0


class FirecrawlTier:
    """Firecrawl markdown scrape as a paid, out-of-band last resort."""

    name: str = "firecrawl"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Firecrawl owns egress + challenge solving.
        from . import Rendered, TierResult  # local import — avoid circular at module load

        key = state.settings.firecrawl_key
        if not key:
            # Defensive: the manifest gates registration on the key, so this
            # path is unreachable in production. Skip silently rather than error.
            return TierResult(body=b"", content_type="text/markdown", status_code=0, final_url=url, skipped=True, verdict=Verdict.other)

        headers = {"Authorization": f"Bearer {key}"}
        # `httpx`, not `fetch_bytes`, is a DECIDED exception — see
        # `docs/architecture/transport-discipline.md`. The breaker is the one
        # thing the shared primitive would have given this tier, so it is taken
        # explicitly rather than forgone.
        try:
            timeout_s = state.settings.request_timeout(_TIMEOUT_S)
            async with (
                paid_api_breaker(state, _API_HOST),
                httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client,
            ):
                resp = await client.post(_API_URL, json={"url": url, "formats": ["markdown"]}, headers=headers)
        except httpx.TimeoutException:
            return TierResult(body=b"", content_type="text/markdown", status_code=0, final_url=url, verdict=Verdict.timeout)
        except httpx.HTTPError:
            return TierResult(body=b"", content_type="text/markdown", status_code=0, final_url=url, verdict=Verdict.connection_error)

        verdict = paid_verdict_for_status(resp.status_code)
        if verdict is not Verdict.ok:
            return TierResult(body=b"", content_type="text/markdown", status_code=resp.status_code, final_url=url, verdict=verdict)

        payload = resp.json()
        data = payload.get("data") or {}
        markdown = (data.get("markdown") or "").strip()
        final_url = (data.get("metadata") or {}).get("sourceURL") or url
        pre_rendered = Rendered(content_md=markdown) if markdown else None
        return TierResult(
            body=markdown.encode("utf-8"),
            content_type="text/markdown",
            status_code=resp.status_code,
            final_url=final_url,
            pre_rendered=pre_rendered,
            verdict=Verdict.ok if pre_rendered is not None else Verdict.length_floor,
        )
