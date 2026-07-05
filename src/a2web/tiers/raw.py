"""Raw tier — HTTP via the shared `http_fetch` primitive.

Maps `FetchOutcome` to a `TierResult`, applying raw's HTML-tier content-type
policy (a 2xx with non-HTML content type yields `content_type_mismatch`).
Conditional GET extras (`etag` / `last_modified`) are forwarded to the
primitive; a 304 surfaces as `conditional_hit`. Per-host purgatory breakers
come from `state.breakers`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from ..models import Verdict
from ..packages.http_fetch import FetchVerdict, fetch_bytes
from ..packages.json_in_script import is_json_content_type, sniff_json_body

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_DEFAULT_TIMEOUT_S = 10


def _verdict_for_status(status: int, content_type: str) -> Verdict:
    """Raw-tier verdict mapping: HTML expected, JSON / PDF / etc. mismatch.

    Kept as a pure function so the tier's policy contract is testable in
    isolation. In the live path the primitive already maps transport
    failures; this function is consulted only when `FetchOutcome.verdict ==
    ok`, but the pure mapping still describes the full status spectrum.
    """
    if status == 404:
        return Verdict.not_found
    if status == 429:
        return Verdict.rate_limited
    if status >= 500:
        return Verdict.connection_error
    if status >= 400:
        return Verdict.connection_error
    # A JSON response is first-class content, not a mismatch: it is synthesized
    # to markdown downstream (json-endpoint-direct-routing), never escalated to
    # the jina HTML reader (which mangles JSON into a false length_floor). This
    # carve-out is evaluated BEFORE the non-HTML mismatch check.
    if is_json_content_type(content_type):
        return Verdict.ok
    if "html" not in content_type.lower():
        return Verdict.content_type_mismatch
    return Verdict.ok


# Map the primitive's transport verdict to the domain Verdict at the tier
# boundary. The values overlap by name; this dict makes the boundary explicit
# and keeps `Verdict` out of the `packages/` layer.
_TRANSPORT_TO_DOMAIN: dict[FetchVerdict, Verdict] = {
    FetchVerdict.ok: Verdict.ok,
    FetchVerdict.not_found: Verdict.not_found,
    FetchVerdict.rate_limited: Verdict.rate_limited,
    FetchVerdict.connection_error: Verdict.connection_error,
    FetchVerdict.timeout: Verdict.timeout,
    FetchVerdict.proxy_unavailable: Verdict.proxy_unavailable,
}


class RawTier:
    """Default tier for any URL — curl_cffi via the shared primitive."""

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

        request_headers = {"User-Agent": state.settings.default_ua}
        host = urlparse(url).hostname or ""
        breaker = await state.breakers.get_breaker(host) if state.breakers is not None and host else None
        # Forward only the keys the primitive understands.
        primitive_extras: dict[str, str] | None = None
        if conditional_extras:
            primitive_extras = {
                k: v for k, v in conditional_extras.items() if k in ("etag", "last_modified") and isinstance(v, str)
            } or None

        outcome = await fetch_bytes(
            url,
            headers=request_headers,
            timeout_s=_DEFAULT_TIMEOUT_S,
            proxy_url=proxy_url,
            cookies=cookies,
            conditional_extras=primitive_extras,
            breaker=breaker,
        )

        # 304 conditional hit — empty body, caller reuses cached body.
        if outcome.conditional_hit:
            return TierResult(
                body=b"",
                content_type=outcome.content_type,
                status_code=304,
                final_url=outcome.final_url,
                headers=outcome.headers,
                conditional_hit=True,
                verdict=Verdict.ok,
            )

        # Transport failure — surface the mapped domain verdict.
        if outcome.verdict is not FetchVerdict.ok:
            return TierResult(
                body=outcome.body,
                content_type=outcome.content_type,
                status_code=outcome.status_code,
                final_url=outcome.final_url,
                headers=outcome.headers,
                verdict=_TRANSPORT_TO_DOMAIN[outcome.verdict],
            )

        # 2xx response — apply raw's HTML-tier content-type policy.
        verdict = _verdict_for_status(outcome.status_code, outcome.content_type)
        content_type = outcome.content_type
        # Recover a JSON payload served under a non-JSON content-type (a
        # misconfigured API returning JSON as text/html / text/plain): sniff the
        # 2xx body; if it parses as JSON, normalize the content-type to
        # application/json so the orchestrator synthesizes it in-place instead of
        # running trafilatura over JSON or escalating to the jina HTML reader
        # (both mangle it into a false length_floor). The prefix-guarded sniff
        # only decodes bodies opening with `{`/`[`, and real HTML never parses as
        # JSON, so this only ever upgrades a genuine JSON body.
        if (
            verdict in (Verdict.ok, Verdict.content_type_mismatch)
            and not is_json_content_type(content_type)
            and sniff_json_body(outcome.body)
        ):
            verdict = Verdict.ok
            content_type = "application/json"
        return TierResult(
            body=outcome.body,
            content_type=content_type,
            status_code=outcome.status_code,
            final_url=outcome.final_url,
            headers=outcome.headers,
            verdict=verdict,
        )
