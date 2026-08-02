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

from http_fetch import FetchVerdict, fetch_bytes

from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_BASE_URL = "https://r.jina.ai/"
_READER_HOST = "r.jina.ai"
_TIMEOUT_S = 15.0

# Map the primitive's transport verdict to a domain Verdict — and note that
# EVERY signal on this path is about `r.jina.ai`, not about the target. That is
# the whole reason this table is not `raw.py`'s.
#
# `dns_error` is the one that matters. `raw.py` maps it straight through because
# there the unresolvable name IS the target, and `Verdict.dns_error` is terminal
# by design (the planner leaves it alone — a real browser cannot resolve a
# nonexistent domain either). Here the unresolvable name is the READER. Passing
# it through would tell the planner the target does not exist, terminally, on
# evidence that says nothing about the target at all — an ADR-0009 laundering,
# in the direction that silences the fetch. The reader being unreachable is a
# connection failure of this tier, and the ladder must be free to continue.
_TRANSPORT_TO_DOMAIN: dict[FetchVerdict, Verdict] = {
    FetchVerdict.ok: Verdict.ok,
    FetchVerdict.not_found: Verdict.not_found,
    FetchVerdict.rate_limited: Verdict.rate_limited,
    FetchVerdict.connection_error: Verdict.connection_error,
    FetchVerdict.dns_error: Verdict.connection_error,
    FetchVerdict.timeout: Verdict.timeout,
    FetchVerdict.proxy_unavailable: Verdict.proxy_unavailable,
}

# jina wraps an upstream error as its OWN HTTP 200 with a body stub of the shape
# `Target URL returned error <status>: <reason>`. Decode the real upstream status
# generically (any 3-digit code — enumerate-by-status is what let a fixed 40[13]
# miss 404 once). Tier-truthfulness contract: a retrieved error page surfaces its
# real upstream status, never `ok`.
#
# The guard against a FALSE wrapper (an article that merely QUOTES the stub
# string) is POSITIONAL, not length-based. It used to be a 2048-byte ceiling
# (`_STUB_MAX_BODY`) and that was the wrong measurement — do not reintroduce one.
# Length only ever correlated with the real discriminator, and a2web's OWN
# `X-Return-Format: markdown` request header (set in `fetch` below) inflates the
# wrapper body past any fixed ceiling: one real 404 page measured 1467 bytes on a
# bare request and 3030 with that header. a2web's own header silently disarmed
# a2web's own guard, laundering a live upstream 404 into `ok` with
# `confidence: high` and no terminal story at all.
#
# Position IS the discriminator. jina emits its metadata (`Title:`,
# `URL Source:`, `Published Time:`, `Warning: ...`) in a header block, then the
# `Markdown Content:` separator, then the retrieved body. A wrapper stub is
# ALWAYS in the header; a quotation is ALWAYS in the body. Searching the header
# region alone is correct at any body size, in both directions.
_UPSTREAM_ERROR_RE = re.compile(r"Target URL returned error (\d{3})")
_BODY_SEPARATOR = "Markdown Content:"


def _wrapper_header(text: str) -> str:
    """The region where jina states its own metadata, before the retrieved body.

    No separator means jina returned metadata with nothing after it — the whole
    response is header, so search all of it.
    """
    head, sep, _ = text.partition(_BODY_SEPARATOR)
    return head if sep else text


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
        del conditional_extras, kwargs
        # `conditional_extras` is DROPPED, deliberately and permanently. a2web's
        # cache is keyed `(url, profile_hash)` and records nothing about which
        # tier produced the entry, so an `etag` in hand may well have come from
        # a raw fetch of the ORIGIN. Sending it to `r.jina.ai` asks a
        # conditional question about a different resource, and a `304` on that
        # question means "the reader's rendering is unchanged", which is not
        # what the caller would reuse. Forwarding these is not an improvement
        # waiting to be made; it is a correctness bug waiting to be introduced.
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

        # The breaker is keyed on `r.jina.ai`, NOT the target host — this tier
        # only ever dials the reader. A target-host breaker would be the SAME
        # breaker the raw tier trips, so a host that just failed on raw would
        # short-circuit jina before it was tried: the ladder's second rung
        # disabled by the first rung's failure, which is the opposite of what a
        # fallback tier is for.
        breaker = await state.breakers.get_breaker(_READER_HOST) if state.breakers is not None else None

        outcome = await fetch_bytes(
            _BASE_URL + url,
            headers=headers,
            timeout_s=state.settings.request_timeout(_TIMEOUT_S),
            proxy_url=proxy_url,
            breaker=breaker,
        )

        if outcome.verdict is not FetchVerdict.ok:
            return TierResult(
                body=b"",
                content_type="text/markdown",
                status_code=outcome.status_code,
                final_url=url,
                verdict=_TRANSPORT_TO_DOMAIN[outcome.verdict],
            )

        verdict = _verdict_for_status(outcome.status_code)
        # jina serves UTF-8 markdown; `errors="replace"` so a byte-level oddity
        # degrades one character rather than voiding the whole tier.
        markdown = outcome.body.decode("utf-8", errors="replace") if verdict == Verdict.ok else ""
        status_code = outcome.status_code
        from . import Rendered  # local — avoid circular

        # Tier-truthfulness: a jina 200 whose body is a wrapper stub is an
        # UPSTREAM error, not real content. Decode the real status, surface it,
        # and drop the stub body so the tier never falsely wins the loop. Scoped
        # to jina's own header region, so an article quoting the stub in its BODY
        # is safe at any length (see the note on `_BODY_SEPARATOR` above).
        if verdict == Verdict.ok:
            stub = _UPSTREAM_ERROR_RE.search(_wrapper_header(markdown))
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
            headers={k.lower(): v for k, v in outcome.headers.items()},
            pre_rendered=pre_rendered,
            verdict=verdict,
        )
