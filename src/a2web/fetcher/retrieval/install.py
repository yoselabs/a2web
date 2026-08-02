"""The single write site for the transport half of a retrieval result."""

from __future__ import annotations

from dataclasses import dataclass

from ...tiers import Rendered
from ..context import FetchContext


@dataclass(frozen=True, slots=True)
class TierInstall:
    """The transport half of a retrieval result — the six fields every path writes.

    Written by five sites before this type existed, in four different orders and
    with two of them silently omitting a field. `_install_rendered_fields` already
    collapsed the CONTENT half after a live bug (`links` added to one of four
    copies, so `other_pages` was unreachable on the common escalation path) and
    explicitly left the transport half alone. This is that half.

    What is deliberately NOT here: `etag`/`last_modified` (the tier loop only —
    they come off response headers no escalation has), the archive snapshot
    dates, and the handler's measured counts. Those are genuinely per-source, and
    folding them in would force `install` to invent a clearing semantics — write
    `etag=None` from the browser path and a conditional-request token acquired
    upstream disappears. A chokepoint for the duplicated set; not a god-setter.
    """

    body: bytes
    content_type: str
    final_url: str
    tier_used: str
    status_code: int
    pre_rendered: Rendered | None = None
    #: True when this install lands AFTER `_phase_extract` has run — the
    #: pipeline-region divergence (design D6), stated rather than implied by
    #: which function you happened to call. Pre-extract installs put the body
    #: down and let extraction fill the content half; post-extract installs have
    #: nothing downstream to fill it, so they must install it here.
    post_extract: bool = False


def install(fc: FetchContext, ti: TierInstall) -> None:
    """The single write site for the transport half of a retrieval result."""
    if ti.post_extract:
        assert ti.pre_rendered is not None  # noqa: S101 — a post-extract install with no content installs nothing
        _install_rendered_fields(fc, ti.pre_rendered)
    fc.body = ti.body
    fc.content_type = ti.content_type
    fc.final_url = ti.final_url
    fc.tier_used = ti.tier_used
    fc.status_code = ti.status_code
    fc.pre_rendered_payload = ti.pre_rendered


def _install_rendered_fields(fc: FetchContext, pre: Rendered) -> None:
    """Copy a pre-rendered payload's content fields onto the context.

    THE ONLY PLACE THIS COPY IS WRITTEN. There were FOUR, and they disagreed:
    `_phase_extract` (the tier won the loop), `_dispatch_archive`,
    `_escalate_browser` (the gate said escalate), and `_escalate_paid`. Adding a
    field to `Rendered` meant remembering all four, and `links` was added to
    exactly one — so the fix meant to make `other_pages` reachable did nothing on
    any page that reached the browser by ESCALATION rather than by winning the
    tier loop. That is the common path: a handler wins, the gate says
    `length_floor`, the browser escalates. Measured on
    `arxiv.org/list/cs.CL/recent` after that fix shipped: `fc.links == 0`.

    The guard written for it could not see this — it tested the extraction seam,
    not the install. One copy is what makes a guard's coverage honest: there is
    now a single line to get wrong.

    The transport half used to be excluded from here with the note that "the
    escalation paths set them from their tier result". That was true and was the
    problem: five paths set them, in four orders, one of them omitting
    `status_code`. `TierInstall` + `install` is now that half's single site, and
    `install(post_extract=True)` calls THIS function — so a post-extract path
    gets both halves from one call. `_phase_extract` still calls this one alone,
    which is the reason the split exists: on the pre-extract path the transport
    fields are already down and extraction only fills the content.
    """
    fc.content_md = pre.content_md
    fc.title = pre.title
    fc.byline = pre.byline
    fc.headings = pre.headings
    fc.links = pre.links
