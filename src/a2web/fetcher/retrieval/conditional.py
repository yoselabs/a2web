"""Conditional requests: the validators we send, and what a 304 back means.

Two halves of one protocol, and they were 80 lines apart inside
`_phase_tier_loop` — `conditional_extras` built at the top of the tier
iteration, the two 304 branches read after the dispatch returned. Lifted by
`decompose-fetcher-into-files` §7; the walk's job is the order of the tiers, not
HTTP revalidation semantics.

**Both 304 branches live here because they are one decision, not two.** A 304
is only meaningful relative to the cached row that produced the validators, so
"reuse the body" and "this 304 is unusable" are the two answers to a single
question — *does the copy this response refers to still exist?* Splitting them
is how the second one came to be missing in the first place.
"""

from __future__ import annotations

from enum import Enum

from ...decision_log import ObservationKind
from ...models import CacheState, Diagnostic, Verdict
from ...tiers import TierResult
from ..context import FetchContext
from ..telemetry import _host


class Conditional(Enum):
    """What the tier walk should do with the response it just received."""

    not_conditional = "not_conditional"  # not a 304 — fall through to normal handling
    unusable = "unusable"  # a 304 with no cached row — skip to the next tier
    reused = "reused"  # cached body installed — the fetch is done


def build_validators(fc: FetchContext) -> dict[str, str] | None:
    """The `If-None-Match` / `If-Modified-Since` inputs for this hop, if any.

    `None` (rather than `{}`) when there is no cached row, so a tier can tell
    "no validators available" from "a row exists but carried neither header".
    """
    if fc.cached_row is None:
        return None
    extras: dict[str, str] = {}
    if fc.cached_row.etag:
        extras["etag"] = fc.cached_row.etag
    if fc.cached_row.last_modified:
        extras["last_modified"] = fc.cached_row.last_modified
    return extras


def resolve_conditional(
    fc: FetchContext,
    tier_result: TierResult,
    *,
    tier_name: str,
    tier_start_ms: int,
    tier_dur_ms: int,
    proxy_id: str | None,
) -> Conditional:
    """Classify a possible 304 and apply its effect."""
    if not (tier_result.status_code == 304 and tier_result.conditional_hit):
        return Conditional.not_conditional
    if fc.cached_row is None:
        _record_unusable(fc, tier_name=tier_name, tier_start_ms=tier_start_ms, tier_dur_ms=tier_dur_ms, proxy_id=proxy_id)
        return Conditional.unusable
    _reuse_cached_body(fc, tier_name=tier_name, tier_start_ms=tier_start_ms, tier_dur_ms=tier_dur_ms, proxy_id=proxy_id)
    return Conditional.reused


def _record_unusable(fc: FetchContext, *, tier_name: str, tier_start_ms: int, tier_dur_ms: int, proxy_id: str | None) -> None:
    """A 304 with NO cached row behind it is unusable, and must never be mistaken for content.

    The tier is telling the truth — "not modified, reuse your copy" — but there
    is no copy, so the body is empty and there is nothing to reuse.

    Before this branch existed the reuse condition below simply failed and the
    empty-body, `Verdict.ok` result FELL THROUGH to `install()`, gating as
    `status: ok` with `content_md: ""` and the narrative `raw → ok (9ms)`. An
    empty result reported as success is the ADR-0009 harm, and the caller had no
    hint that anything was wrong.

    a2web only sends `If-None-Match` / `If-Modified-Since` when it HAS the row,
    so in production this means the row was evicted between the request being
    built and the response arriving. It is also exactly what a replayed cassette
    does when it froze a 304
    (`eval/findings_2026-08-03-the-cassette-that-froze-a-304.md`).

    Treated as a tier that produced nothing usable, so the cascade continues to
    the next rung — which is what the cascade is for. NOT a wall, NOT a 404:
    `other` is the honest verdict for an unusable protocol state.
    """
    fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.other)
    fc.diagnostics.append(
        Diagnostic(
            t_ms=tier_start_ms,
            step=tier_name,
            engine="curl_cffi" if tier_name == "raw" else None,
            host=_host(fc.url),
            proxy=proxy_id,
            verdict=Verdict.other,
            dur_ms=tier_dur_ms,
            extra={"conditional_hit": "unmatched", "status_code": 304},
        )
    )


def _reuse_cached_body(fc: FetchContext, *, tier_name: str, tier_start_ms: int, tier_dur_ms: int, proxy_id: str | None) -> None:
    """Conditional 304 → reuse the cached body.

    A distinct return path: no after-tier action, no further tiers, no
    extract/gate ahead.

    This writes part of the transport half WITHOUT going through `install()`,
    which is the one standing exemption in
    `tests/architecture/test_transport_install_chokepoint.py`. The reason is
    that there is no tier result to install — the body came from sqlite, and
    `status_code = 200` is a logical hit rather than anything a server said.
    Routing it through `install` would additionally write `final_url`, which
    this path deliberately leaves alone.
    """
    fc.body = fc.cached_row.body if fc.cached_row else b""
    fc.content_type = (fc.cached_row.content_type if fc.cached_row else None) or "text/html"
    fc.status_code = 200  # logical hit
    fc.cache_state = CacheState.hit
    fc.etag = fc.cached_row.etag if fc.cached_row else None
    fc.last_modified = fc.cached_row.last_modified if fc.cached_row else None
    fc.tier_used = tier_name
    fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.ok)
    fc.diagnostics.append(
        Diagnostic(
            t_ms=tier_start_ms,
            step=tier_name,
            engine="curl_cffi",
            host=_host(fc.url),
            proxy=proxy_id,
            verdict=Verdict.ok,
            dur_ms=tier_dur_ms,
            extra={"conditional_hit": "true"},
        )
    )
