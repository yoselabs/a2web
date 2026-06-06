"""record_extract detection — locate the dominant repeated record region.

Pure HTML -> records. This module MUST NOT import from `a2web.<domain>`.

trafilatura is an article extractor: it locates one main-content node and
discards repeated DOM structure as boilerplate. On a listing / index / thread
page there is no single article — the page *is* N repeated records — so
trafilatura guts it. This module recovers the records.

Detection is **tree-aware**: each `(tag, first-class-token)` signature is
counted document-wide, not only among the direct children of one container,
so a recursively nested record region (a threaded comment tree) is located as
well as a flat sibling list. The occurrences of the chosen signature are the
records, rooted at their lowest common ancestor; each is rendered at its
nesting depth using its **own scope** (text/links excluding nested
same-signature child-records).

A signature must clear three guards to be a candidate — non-empty class
token, parent-signature consistency, heading presence — and an ancestor
tie-break resolves a near-tie in favour of the outer wrapper. The detector
self-gates: when no signature clears the guards, `extract_records` returns
`None` and the caller falls through (an article, a near-empty JS shell, a
reference doc — none is a record region).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from statistics import median

import lxml.html

from .models import Record, RecordSet
from .render import render_record

# A record region needs at least this many repeated, content-bearing records.
_MIN_RECORDS = 5
# A content-bearing record carries more than this many chars of own-scope text.
_MIN_RECORD_TEXT = 20
# Per-record text is capped in the ranking score so a few huge records do not
# outweigh a genuine many-record listing.
_MEDIAN_TEXT_CAP = 400
# Hard cap on rendered / emitted records — parity with the JSON-synth row cap.
_MAX_RECORDS = 50
# Guard (b): the records must share one dominant parent signature.
_CONSISTENCY_MIN = 0.70
# Guard (c): at least this fraction of records must carry a heading.
_HEADING_FRAC_MIN = 0.50
# Candidates scoring within this band of the best are "tied" — the ancestor
# tie-break then prefers the outer wrapper.
_TIE_BAND = 0.85
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# A `(tag, first-class-token)` structural signature.
_Signature = tuple[str, str]


@dataclass(slots=True)
class _Candidate:
    """A scratch candidate signature evaluated during detection."""

    sig: _Signature
    content: list[lxml.html.HtmlElement]
    score: float
    consistency: float
    heading_frac: float


def _signature(el: lxml.html.HtmlElement) -> _Signature:
    if not isinstance(el.tag, str):
        return ("", "")
    classes = (el.get("class") or "").split()
    return (el.tag, classes[0] if classes else "")


def _el_label(el: lxml.html.HtmlElement) -> str:
    tag, cls = _signature(el)
    return f"{tag or '?'}.{cls or '-'}"


def _collapse(text: str) -> str:
    return " ".join(text.split())


# Strikethrough tags — their text is a superseded value (e.g. an original/list
# price crossed out). Marked as markdown `~~…~~` so the projection preserves the
# list-vs-sale distinction for the extractor instead of flattening it away.
_STRIKE_TAGS = frozenset({"del", "s", "strike"})


def _apply_markup(el: lxml.html.HtmlElement, text: str) -> str:
    """Wrap answer-bearing markup so it survives the text projection."""
    if isinstance(el.tag, str) and el.tag in _STRIKE_TAGS and text.strip():
        return f"~~{text}~~"
    return text


def _own_text(el: lxml.html.HtmlElement, record_sig: _Signature) -> str:
    """Concatenated text of `el`'s own scope — descending into children but
    pruning any nested same-signature child-record subtree (its text belongs
    to that child's own scope, not the parent's).

    A separator is inserted at **element boundaries** when two adjacent
    contributions would otherwise fuse (neither side carries whitespace), so
    distinct inline values — a price and an abutting discount badge — stay
    distinguishable. Text-flow continuity is preserved: an element's tail text
    concatenates normally (`<b>Hel</b>lo` stays `Hello`); only element
    contributions are guarded. This is the structural elimination of the
    value-blind no-separator projection (ADR-0003); it is content-agnostic —
    no branch inspects whether a fragment looks like a price or percentage.
    """
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if isinstance(child.tag, str) and _signature(child) != record_sig:
            child_text = _apply_markup(child, _own_text(child, record_sig))
            if child_text:
                if parts and not parts[-1][-1:].isspace() and not child_text[:1].isspace():
                    parts.append(" ")
                parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _own_elements(el: lxml.html.HtmlElement, record_sig: _Signature) -> Iterator[lxml.html.HtmlElement]:
    """Yield `el`'s own-scope descendant elements, skipping nested
    same-signature child-record subtrees entirely."""
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if _signature(child) == record_sig:
            continue
        yield child
        yield from _own_elements(child, record_sig)


def _own_links(el: lxml.html.HtmlElement, record_sig: _Signature) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for d in _own_elements(el, record_sig):
        if d.tag == "a":
            href = d.get("href")
            if href:
                out.append((_collapse(d.text_content()), href))
    return tuple(out)


def _own_has_link(el: lxml.html.HtmlElement, record_sig: _Signature) -> bool:
    return any(d.tag == "a" and d.get("href") for d in _own_elements(el, record_sig))


def _own_has_heading(el: lxml.html.HtmlElement, record_sig: _Signature) -> bool:
    return any(d.tag in _HEADING_TAGS or d.get("role") == "heading" for d in _own_elements(el, record_sig))


def _heading(el: lxml.html.HtmlElement, record_sig: _Signature) -> tuple[str, tuple[str, str] | None] | None:
    """The record's heading — its own-scope text and (optionally) its first
    anchor's `(anchor_text, href)`.

    Returns:
      * `(heading_text, link)` when an own-scope heading is found, where
        `link` is the first anchor inside it (or `None` if the heading has
        no link).
      * `None` when no own-scope heading exists at all.
    """
    for d in _own_elements(el, record_sig):
        if d.tag in _HEADING_TAGS or d.get("role") == "heading":
            heading_text = _collapse(d.text_content())
            if not heading_text:
                continue
            for a in d.iter("a"):
                href = a.get("href")
                if href:
                    return heading_text, (_collapse(a.text_content()), href)
            return heading_text, None
    return None


def _depth(el: lxml.html.HtmlElement, record_sig: _Signature) -> int:
    """Count of `el`'s ancestors that share the record signature."""
    d = 0
    p = el.getparent()
    while p is not None:
        if _signature(p) == record_sig:
            d += 1
        p = p.getparent()
    return d


def _parent_signature(el: lxml.html.HtmlElement) -> _Signature:
    p = el.getparent()
    return _signature(p) if p is not None else ("", "")


def _lca(elements: list[lxml.html.HtmlElement]) -> lxml.html.HtmlElement | None:
    """Lowest common ancestor of `elements` — the root of the record region."""

    def ancestors(e: lxml.html.HtmlElement) -> list[lxml.html.HtmlElement]:
        chain: list[lxml.html.HtmlElement] = []
        cur: lxml.html.HtmlElement | None = e
        while cur is not None:
            chain.append(cur)
            cur = cur.getparent()
        return list(reversed(chain))

    common = ancestors(elements[0])
    for e in elements[1:]:
        aset = set(ancestors(e))
        common = [c for c in common if c in aset]
    return common[-1] if common else None


def _build_record(el: lxml.html.HtmlElement, record_sig: _Signature, depth: int) -> Record:
    text = _collapse(_own_text(el, record_sig))
    links = _own_links(el, record_sig)
    heading = _heading(el, record_sig)
    if heading is not None:
        heading_text, heading_link = heading
    else:
        # No own-scope heading. Keep the legacy heading-link fallback so
        # `_records_to_next_links` still gets a usable source link, but leave
        # `heading_text` unset so the renderer falls through to the text-led row.
        heading_text = None
        heading_link = max(links, key=lambda link: len(link[0])) if links else None
    return Record(
        text=text,
        links=links,
        heading_text=heading_text,
        heading_link=heading_link,
        depth=depth,
        markdown=render_record(
            text,
            links,
            depth,
            heading_text=heading_text,
            heading_link=heading_link,
        ),
    )


def _evaluate(sig: _Signature, members: list[lxml.html.HtmlElement]) -> _Candidate | None:
    """Score one signature group and compute its guard metrics, or `None`
    when it cannot be a record region."""
    tag, cls = sig
    if not tag or not cls:  # guard (a): non-empty class token
        return None
    if len(members) < _MIN_RECORDS:
        return None
    content: list[lxml.html.HtmlElement] = []
    text_lens: list[int] = []
    for el in members:
        own = _collapse(_own_text(el, sig))
        if len(own) > _MIN_RECORD_TEXT and _own_has_link(el, sig):
            content.append(el)
            text_lens.append(len(own))
    if len(content) < _MIN_RECORDS:
        return None
    parent_sigs = Counter(_parent_signature(el) for el in content)
    consistency = parent_sigs.most_common(1)[0][1] / len(content)
    heading_frac = sum(_own_has_heading(el, sig) for el in content) / len(content)
    score = len(content) * min(median(text_lens), _MEDIAN_TEXT_CAP)
    return _Candidate(
        sig=sig,
        content=content,
        score=score,
        consistency=consistency,
        heading_frac=heading_frac,
    )


def _select(candidates: list[_Candidate]) -> _Candidate | None:
    """Apply guards (b) + (c), then pick the best with an ancestor tie-break."""
    passed = [c for c in candidates if c.consistency >= _CONSISTENCY_MIN and c.heading_frac >= _HEADING_FRAC_MIN]
    if not passed:
        return None
    passed.sort(key=lambda c: c.score, reverse=True)
    best = passed[0].score
    tied = [c for c in passed if c.score >= _TIE_BAND * best]
    # Ancestor tie-break: prefer the candidate whose signature is the parent
    # signature of another tied candidate — the outer wrapper carries the
    # full record / the threading.
    for c in tied:
        if any(other is not c and c.sig == _parent_signature(other.content[0]) for other in tied):
            return c
    return tied[0]


def extract_records(html: str, base_url: str = "") -> RecordSet | None:
    """Locate the dominant repeated record region and extract its records.

    Returns `None` when no signature clears the detection guards — an article,
    a near-empty JS shell, a reference doc. The caller treats `None` as "this
    page is not a listing; fall through to the next extraction source".

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

    # Document-wide signature grouping — one pass over the tree.
    groups: dict[_Signature, list[lxml.html.HtmlElement]] = defaultdict(list)
    for el in tree.iter():
        if isinstance(el.tag, str):
            groups[_signature(el)].append(el)

    candidates: list[_Candidate] = []
    for sig, members in groups.items():
        candidate = _evaluate(sig, members)
        if candidate is not None:
            candidates.append(candidate)

    chosen = _select(candidates)
    if chosen is None:
        return None

    sig = chosen.sig
    members = chosen.content[:_MAX_RECORDS]
    records: list[Record] = []
    max_depth = 0
    for el in members:
        depth = _depth(el, sig)
        max_depth = max(max_depth, depth)
        records.append(_build_record(el, sig, depth))

    container = _lca(members)
    return RecordSet(
        records=tuple(records),
        container=_el_label(container) if container is not None else "",
        child_signature=f"{sig[0]}.{sig[1] or '-'}",
        max_depth=max_depth,
    )
