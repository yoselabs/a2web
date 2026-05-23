"""Twitter / X status handler — fetches via configured Nitter mirror rotation.

Twitter / X has no working public unauthenticated path: the raw HTML is a JS
shell, the public API is paid, and the browser tier hits the login wall.
Nitter is a FOSS read-only frontend that scrapes Twitter and serves clean
server-rendered HTML for tweet + reply threads. Public instances rotate and
die regularly, so the handler is rotation-aware with per-instance circuit
breakers (reusing the existing `purgatory` infrastructure used elsewhere).

The handler is `matches=False` when `nitter_instances` is empty — graceful
disable so an unconfigured a2web falls through to raw + browser tiers
without errors. Operators opt in by setting `A2WEB_NITTER_INSTANCES`
(comma-separated) or `nitter_instances:` in YAML.
"""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog
import trafilatura

from ..models import Heading, Verdict
from ..packages.http_fetch import FetchVerdict, fetch_bytes

_LOG = structlog.get_logger("a2web.handlers.twitter")

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_STATUS_PATH_RE = re.compile(r"^/(?P<user>[^/]+)/status/(?P<id>\d+)(?:/.*)?$")
_TWITTER_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com"})
_DEFAULT_TIMEOUT_S = 5


def _is_twitter_host(host: str) -> bool:
    return host in _TWITTER_HOSTS


class TwitterHandler:
    """Tier-0 handler for X / Twitter status URLs via Nitter."""

    name: str = "site_handler:twitter"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        parsed = urlparse(url)
        if not _is_twitter_host(parsed.hostname or ""):
            return False
        if not _STATUS_PATH_RE.match(parsed.path or ""):
            return False
        # `nitter_instances` could be consulted here now that settings is
        # threaded through `matches()`, but the empty-list short-circuit lives
        # in fetch() — leaving this unconditional keeps matches() behaviour
        # unchanged. Tightening it is a separate change.
        return True

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import TierResult

        instances = list(state.settings.nitter_instances)
        if not instances:
            # Treat as no-match: orchestrator falls through to raw + browser.
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=url,
                no_match=True,
            )

        parsed = urlparse(url)
        m = _STATUS_PATH_RE.match(parsed.path or "")
        if m is None:
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=url,
                no_match=True,
            )
        user, status_id = m.group("user"), m.group("id")

        # Per-fetch shuffle keeps load distributed without persistent state.
        random.shuffle(instances)

        last_verdict = Verdict.connection_error
        for instance in instances:
            breaker = await state.breakers.get_breaker(f"nitter:{instance}")
            try:
                async with breaker:
                    verdict, result = await _try_instance(
                        instance=instance,
                        user=user,
                        status_id=status_id,
                        state=state,
                    )
                    if verdict == Verdict.ok and result is not None:
                        return result
                    last_verdict = verdict
                    # Raise to register a failure with the breaker. The
                    # outer `try` catches this and moves to the next
                    # instance.
                    raise _NitterInstanceFailure(verdict)
            except _NitterInstanceFailure:
                continue
            except Exception as exc:
                # Breaker open OR unexpected error — skip this instance.
                _LOG.debug("nitter_instance_skipped", instance=instance, error=str(exc))
                continue

        return _empty_result(url, last_verdict)


class _NitterInstanceFailure(Exception):
    """Raised inside the breaker context to register a non-ok response."""

    def __init__(self, verdict: Verdict):
        self.verdict = verdict
        super().__init__(f"nitter instance returned {verdict}")


async def _try_instance(
    *,
    instance: str,
    user: str,
    status_id: str,
    state: AppState,
) -> tuple[Verdict, TierResult | None]:
    """Issue one GET against an instance. Returns (verdict, result-or-None)."""
    from ..tiers import Rendered, TierResult

    base = instance.rstrip("/")
    nitter_url = f"{base}/{user}/status/{status_id}"

    outcome = await fetch_bytes(
        nitter_url,
        headers={"User-Agent": state.settings.default_ua},
        timeout_s=_DEFAULT_TIMEOUT_S,
    )

    if outcome.verdict is FetchVerdict.timeout:
        return Verdict.timeout, None
    if outcome.verdict is FetchVerdict.not_found:
        # Specific tweet not on this instance — try the next one.
        return Verdict.not_found, None
    if outcome.verdict is FetchVerdict.rate_limited:
        return Verdict.rate_limited, None
    if outcome.verdict is not FetchVerdict.ok:
        return Verdict.connection_error, None

    html = outcome.body.decode("utf-8", errors="replace")
    if not html:
        return Verdict.length_floor, None

    markdown = (
        trafilatura.extract(
            html,
            url=nitter_url,
            output_format="markdown",
            include_comments=True,
            include_tables=False,
        )
        or ""
    )
    if not markdown:
        return Verdict.length_floor, None

    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata else None) or f"@{user}"
    author = (metadata.author if metadata else None) or user
    byline = author if author else None

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))

    return Verdict.ok, TierResult(
        body=outcome.body,
        content_type="text/html",
        status_code=outcome.status_code,
        final_url=nitter_url,
        headers=outcome.headers,
        pre_rendered=Rendered(
            content_md=markdown,
            title=title,
            byline=byline,
            headings=headings,
        ),
        verdict=Verdict.ok,
    )


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
