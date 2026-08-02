"""Records and LLM output into `NextLink`s, and the ADR-0014 validation."""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import urlparse

from record_mine import Record, RecordSet

from ...models import NextLink, NextLinkKind
from ...packages.llm_extract import LlmNextLink

# An anchor that reads like a comment count — "12 comments", "1 comment".
_COMMENT_COUNT_RE = re.compile(r"\b\d+\s*comments?\b", re.IGNORECASE)
# Archive-mirror hosts whose links shadow the discussed page in a record's
# link set — skipped as next_links candidates.
_ARCHIVE_MIRROR_HOSTS = frozenset(
    {
        "web.archive.org",
        "archive.org",
        "ghostarchive.org",
        "archive.ph",
        "archive.today",
        "archive.is",
    }
)


def _is_archive_mirror(url: str) -> bool:
    """True when `url` points at a known archive-mirror host."""
    host = (urlparse(url).hostname or "").lower()
    return host in _ARCHIVE_MIRROR_HOSTS or host.endswith(".archive.org")


def _record_discussion_link(record: Record, page_host: str) -> tuple[str, str] | None:
    """A record's discussion permalink — a same-host link whose anchor reads
    like a comment count (`"N comments"`). `None` when the record carries no
    such link (a plain catalog row with only a source link)."""
    for anchor, url in record.links:
        if not _COMMENT_COUNT_RE.search(anchor):
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host or host == page_host:
            return (anchor, url)
    return None


def _heading_link_kind(link: tuple[str, str] | None, *, page_host: str) -> tuple[NextLinkKind, str]:
    """Classify a record's heading link by where it points.

    On-host — the row leads deeper into the same site, so it is the item's own
    page: a `drilldown`. Off-host — the row leads away, which is what an
    aggregator row is for: a `source`, the page it discusses.

    A record with no host (a relative href the miner did not resolve) is read as
    on-host, since a relative link cannot leave the site.
    """
    if link is None:
        return "source", "discussed page"
    link_host = (urlparse(link[1]).hostname or "").lower()
    if not link_host or link_host == page_host or link_host.removeprefix("www.") == page_host.removeprefix("www."):
        return "drilldown", "item page"
    return "source", "discussed page"


def _records_to_next_links(record_set: RecordSet, *, page_url: str) -> list[NextLink]:
    """Domain seam — convert detected records into `NextLink` candidates.

    Catalog-only: a threaded record set is a conversation already inline on
    the page, not a set of drilldown targets, so it emits nothing. Each flat
    record emits up to two candidates — its heading link and a `discussion`
    link (a same-host comment-count permalink). Candidates are deduplicated by
    URL and archive-mirror hosts are skipped.

    **The heading link's kind is decided per record, not fixed.** It was
    hardcoded `("source", "discussed page")` — the aggregator vocabulary, where
    a row points OFF-host at an article the page discusses. The same miner runs
    on catalogs, where a row points ON-host at the item's own detail page: that
    is a `drilldown`, and calling it a source asserts the page is discussing
    something it is in fact selling. Every commerce listing said "source ·
    discussed page", and the JSON-LD `ItemList` path routed straight into it, so
    the mislabel arrived on every `ItemList` catalog too.

    Off-host vs on-host is the discriminator because it is what actually
    separates the two shapes: an aggregator row's whole purpose is to leave the
    host, a catalog row's is to go deeper into it.
    """
    if record_set.is_threaded:
        return []
    page_host = (urlparse(page_url).hostname or "").lower()
    out: list[NextLink] = []
    seen: set[str] = set()
    for record in record_set.records:
        heading_kind, heading_reason = _heading_link_kind(record.heading_link, page_host=page_host)
        candidates: tuple[tuple[tuple[str, str] | None, NextLinkKind, str], ...] = (
            (record.heading_link, heading_kind, heading_reason),
            (_record_discussion_link(record, page_host), "discussion", "discussion thread"),
        )
        for link, kind, reason in candidates:
            if link is None:
                continue
            anchor, url = link
            if url in seen or _is_archive_mirror(url):
                continue
            seen.add(url)
            # No `anchor[:120]` here: `NextLink.anchor` declares `max_length=120`
            # AND a truncating validator, so the hand-rolled slice was a second
            # copy of the model's own bound — the same duplication this module's
            # onward-link cap suffered, one field down.
            out.append(NextLink(anchor=anchor or url, url=url, reason=reason, kind=kind))
    return out


def _to_llm_next_link(nl: NextLink) -> LlmNextLink:
    """Convert a domain `NextLink` into the package boundary `LlmNextLink` shape."""
    return LlmNextLink(anchor=nl.anchor, url=nl.url, reason=nl.reason, kind=nl.kind)


def _validate_llm_next_links_against_markdown(
    llm_next_links: list[LlmNextLink],
    *,
    markdown: str,
    handler_urls: set[str],
) -> tuple[list[NextLink], list[str]]:
    """Validate LLM-supplied URLs appear in the markdown OR were handler-supplied.

    Returns `(validated_NextLinks, dropped_urls)`. URLs that don't appear in
    the markdown AND weren't in `handler_urls` are dropped — defense against
    hallucinated URLs. Pydantic validation runs on the conversion; entries
    failing validation are silently skipped (provider misbehavior, not the
    user's problem).
    """
    validated: list[NextLink] = []
    dropped: list[str] = []
    for nl in llm_next_links:
        # Cheap substring check is enough — markdown links render as `(url)` so a
        # naive `url in markdown` covers `[anchor](url)` AND raw `<url>` forms.
        if nl.url not in markdown and nl.url not in handler_urls:
            dropped.append(nl.url)
            continue
        try:
            validated.append(
                NextLink(
                    anchor=nl.anchor,
                    url=nl.url,
                    reason=nl.reason,
                    kind=cast(NextLinkKind, nl.kind),
                ),
            )
        except Exception:  # pydantic ValidationError; silent drop on provider misbehavior
            dropped.append(nl.url)
    return validated, dropped
