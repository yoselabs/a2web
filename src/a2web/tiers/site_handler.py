"""Site-handler dispatch tier — calls `match_handler(url)` and forwards.

Returns a sentinel `TierResult(no_match=True)` when no handler claims the
URL; the orchestrator skips the diagnostic row and falls through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..handlers import match_handler
from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


class SiteHandlerTier:
    """Dispatcher that routes URLs to the matching site handler, if any."""

    name: str = "site_handler"

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from . import TierResult

        handler = match_handler(url)
        if handler is None:
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=url,
                no_match=True,
                verdict=Verdict.other,
            )
        result = await handler.fetch(url, state=state)
        if result.handler_name is None:
            result.handler_name = handler.name
        return result
