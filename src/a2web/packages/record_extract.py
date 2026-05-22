"""record_extract — locate and extract repeated data records from listing HTML.

Pure HTML -> records. This package MUST NOT import from `a2web.<domain>`.

trafilatura is an article extractor: it locates one main-content node and
discards repeated DOM structure as boilerplate. On a listing / index page
there is no single article — the page *is* N repeated records — so trafilatura
guts it. This package recovers the records: locate the dominant repeated
record region (C1), render it to link-preserving markdown (C2), and expose
each record so the domain seam can populate `next_links`.

The detector is deliberately simple (spike-validated): the dominant record
region is the container whose direct children include the most content-bearing
repeats of one structural signature. No page-type classifier — when no region
clears the content-bearing floor, `extract_records` returns `None` and the
caller falls through.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

import lxml.html

# A record region needs at least this many repeated, content-bearing children.
_MIN_RECORDS = 5
# A content-bearing record carries more than this many chars of visible text.
_MIN_RECORD_TEXT = 20
# Per-record text is capped in the ranking score so a few huge records do not
# outweigh a genuine many-record listing.
_MEDIAN_TEXT_CAP = 400
# Hard cap on rendered / emitted records — parity with the JSON-synth row cap.
_MAX_RECORDS = 50
# Links rendered per record (the first link is often chrome; keep them all,
# but bound the line length).
_MAX_LINKS_PER_RECORD = 10
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@dataclass(slots=True, frozen=True)
class Record:
    """One extracted listing record.

    `links` carries every link in the record (anchor text, href) — the first
    link is frequently chrome (an action button), so none is dropped.
    `primary_link` is the record's most identifying link (a heading link, or
    the longest-anchor link) for `next_links`; it MAY be `None`.
    """

    text: str
    links: tuple[tuple[str, str], ...]
    primary_link: tuple[str, str] | None
    markdown: str


@dataclass(slots=True, frozen=True)
class RecordSet:
    """The located dominant record region and its rendered records."""

    records: tuple[Record, ...]
    container: str
    child_signature: str

    def to_markdown(self) -> str:
        """Render the whole record set to a markdown block."""
        body = "\n".join(r.markdown for r in self.records)
        return f"### Listing ({len(self.records)} records)\n\n{body}"


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _child_signature(el: lxml.html.HtmlElement) -> tuple[str, str]:
    classes = (el.get("class") or "").split()
    return (str(el.tag), classes[0] if classes else "")


def _el_label(el: lxml.html.HtmlElement) -> str:
    classes = (el.get("class") or "").split()
    return f"{el.tag}.{classes[0] if classes else '-'}"


def _record_links(el: lxml.html.HtmlElement) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for a in el.xpath(".//a[@href]"):
        href = a.get("href")
        if href:
            out.append((_collapse(a.text_content()), href))
    return tuple(out)


def _is_content_bearing(el: lxml.html.HtmlElement) -> bool:
    return len(_collapse(el.text_content())) > _MIN_RECORD_TEXT and bool(el.xpath(".//a[@href]"))


def _primary_link(
    el: lxml.html.HtmlElement,
    links: tuple[tuple[str, str], ...],
) -> tuple[str, str] | None:
    """The record's identifying link: a heading link if present, else the
    link with the longest anchor text. The first link is often chrome."""
    for tag in _HEADING_TAGS:
        for a in el.xpath(f".//{tag}//a[@href]"):
            href = a.get("href")
            if href:
                return (_collapse(a.text_content()), href)
    if links:
        return max(links, key=lambda link: len(link[0]))
    return None


def _render_record(text: str, links: tuple[tuple[str, str], ...]) -> str:
    line = f"- {text[:500]}"
    if links:
        rendered = " · ".join(f"[{anchor or href}]({href})" for anchor, href in links[:_MAX_LINKS_PER_RECORD])
        line += f"\n  {rendered}"
    return line


def _build_record(el: lxml.html.HtmlElement) -> Record:
    text = _collapse(el.text_content())
    links = _record_links(el)
    return Record(
        text=text,
        links=links,
        primary_link=_primary_link(el, links),
        markdown=_render_record(text, links),
    )


def extract_records(html: str, base_url: str = "") -> RecordSet | None:
    """Locate the dominant repeated record region and extract its records.

    Returns `None` when no repeated region clears the content-bearing floor —
    an article, a near-empty JS shell, a blocked page. The caller treats
    `None` as "fall through to the next extraction source".

    `base_url`, when given, resolves relative hrefs to absolute URLs.
    """
    if not html or not html.strip():
        return None
    try:
        tree = lxml.html.fromstring(html)
    except (ValueError, SyntaxError):
        return None
    if base_url:
        try:
            tree.make_links_absolute(base_url)
        except (ValueError, SyntaxError):
            pass

    best_score = 0.0
    best: tuple[lxml.html.HtmlElement, tuple[str, str], list[lxml.html.HtmlElement]] | None = None
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        children = [c for c in el if isinstance(c.tag, str)]
        if len(children) < _MIN_RECORDS:
            continue
        groups: dict[tuple[str, str], list[lxml.html.HtmlElement]] = defaultdict(list)
        for c in children:
            groups[_child_signature(c)].append(c)
        for sig, members in groups.items():
            if len(members) < _MIN_RECORDS:
                continue
            content = [c for c in members if _is_content_bearing(c)]
            if len(content) < _MIN_RECORDS:
                continue
            text_lengths = [len(_collapse(c.text_content())) for c in content]
            score = len(content) * min(median(text_lengths), _MEDIAN_TEXT_CAP)
            if score > best_score:
                best_score = score
                best = (el, sig, content)

    if best is None:
        return None
    container, sig, members = best
    records = tuple(_build_record(c) for c in members[:_MAX_RECORDS])
    return RecordSet(
        records=records,
        container=_el_label(container),
        child_signature=f"{sig[0]}.{sig[1] or '-'}",
    )


__all__ = ["Record", "RecordSet", "extract_records"]
