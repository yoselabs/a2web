"""arxiv handler — export.arxiv.org Atom API for clean abstract pages.

Match: `arxiv.org/abs/<id>`. The PR7b playbook rewrites pdf URLs to abs
before this runs, so we don't need to handle pdf paths here.

API: `GET https://export.arxiv.org/api/query?id_list=<id>` returns Atom
XML with one entry per id. Empty entry list = unknown id (not_found).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree as ET

from dom_schema import Extraction, Schema, extract
from dom_schema import Field as DomField
from http_fetch import fetch_bytes

from ..listing_oracle import listing_oracle
from ..log import log_warning
from ..models import Heading, NextLink, Verdict
from ._common import empty_result, map_non_ok

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_ARXIV_ID_RE = re.compile(r"^/abs/([^/?#]+?)(?:v\d+)?/?$", re.IGNORECASE)
_ARXIV_LIST_RE = re.compile(r"^/list/(?P<cat>[A-Za-z][A-Za-z\-\.]*)/(?P<window>\d{4,6}|recent|new)/?$", re.IGNORECASE)
_ARXIV_HOSTS = frozenset({"arxiv.org", "www.arxiv.org"})
_API_URL = "https://export.arxiv.org/api/query"
_LIST_URL = "https://arxiv.org/list"
_TIMEOUT_S = 10.0
# How many listing rows the handler renders. Declared once — the render, the
# `N of M` prose and the sufficiency declaration must not disagree.
_LISTING_RENDER_CAP = 25
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _extract_id(url: str) -> str | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _ARXIV_HOSTS:
        return None
    match = _ARXIV_ID_RE.match(parsed.path or "")
    return match.group(1) if match else None


def _extract_listing(url: str) -> tuple[str, str] | None:
    """Return `(category, window)` for an arxiv `/list/<cat>/<yymm|recent>` URL."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _ARXIV_HOSTS:
        return None
    match = _ARXIV_LIST_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group("cat"), match.group("window")


class ArxivHandler:
    """Tier-0 handler for arxiv.org/abs/<id> and arxiv.org/list/<cat>/<window> URLs."""

    name: str = "site_handler:arxiv"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _extract_id(url) is not None or _extract_listing(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import Rendered, TierResult

        listing = _extract_listing(url)
        if listing is not None:
            return await self._fetch_listing(url, listing=listing, state=state)

        arxiv_id = _extract_id(url)
        if arxiv_id is None:
            return empty_result(url, Verdict.not_found)

        outcome = await fetch_bytes(
            f"{_API_URL}?{urlencode({'id_list': arxiv_id})}",
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=state.settings.request_timeout(_TIMEOUT_S),
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            return non_ok

        try:
            root = ET.fromstring(outcome.body.decode("utf-8", errors="replace"))  # noqa: S314 — arxiv API is trusted
        except ET.ParseError:
            return empty_result(url, Verdict.content_type_mismatch)

        entry = root.find("atom:entry", _NS)
        if entry is None:
            return empty_result(url, Verdict.not_found)

        rendered = _render_entry(entry)

        return TierResult(
            body=outcome.body,
            content_type="application/atom+xml",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
            volatility="live",
        )

    async def _fetch_listing(
        self,
        url: str,
        *,
        listing: tuple[str, str],
        state: AppState,
    ) -> TierResult:
        from ..tiers import Rendered, TierResult

        cat, window = listing
        list_url = f"{_LIST_URL}/{cat}/{window}"
        outcome = await fetch_bytes(
            list_url,
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=state.settings.request_timeout(_TIMEOUT_S),
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            return non_ok

        listing_html = outcome.body.decode("utf-8", errors="replace")
        parsed = _parse_listing(listing_html)
        if parsed.is_rot:
            # The schema stopped describing arXiv. That is a fact about THIS
            # handler, never about the page — so it must not be laundered into a
            # rendered "Papers (0)" with Verdict.ok, which is exactly what the
            # old parser did while returning nothing for every listing URL.
            # A non-ok verdict lets the cascade try another tier, and the
            # captured-fixture test is what turns this into a red build.
            log_warning(
                "handler_schema_rot",
                handler="arxiv",
                url=url,
                missing=sorted(parsed.missing),
            )
            return empty_result(url, Verdict.length_floor)

        entries = parsed.rows
        advertised = listing_oracle(listing_html)
        rendered = _render_listing(cat, window, entries, advertised_total=advertised)
        next_links = _listing_candidates(entries)

        return TierResult(
            body=outcome.body,
            content_type="text/html",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered.from_dict(rendered),
            next_links=next_links,
            verdict=Verdict.ok,
            volatility="live",
            # Both numbers already drive the "Showing 25 of 445" prose; declaring
            # them lets the sufficiency check reach the same conclusion the
            # markdown states. Previously they were computed and discarded, so
            # `listing_partial` never fired on this path.
            items_rendered=min(len(entries), _LISTING_RENDER_CAP),
            items_advertised=advertised,
        )


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return re.sub(r"\s+", " ", el.text).strip()


def _render_entry(entry: ET.Element) -> dict[str, object]:
    title = _text(entry.find("atom:title", _NS))
    summary = _text(entry.find("atom:summary", _NS))

    authors: list[str] = []
    for author_el in entry.findall("atom:author", _NS):
        name = _text(author_el.find("atom:name", _NS))
        if name:
            authors.append(name)
    byline = ", ".join(authors) if authors else None

    categories: list[str] = []
    for cat_el in entry.findall("atom:category", _NS):
        term = cat_el.attrib.get("term")
        if term:
            categories.append(term)

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if byline:
        parts.append(f"_{byline}_\n")
    if summary:
        parts.append(summary + "\n")
    if categories:
        parts.append("\n## Categories\n")
        for cat in categories:
            parts.append(f"- {cat}")

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    if categories:
        headings.append(Heading(level=2, text="Categories"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title or None,
        "byline": byline,
        "headings": headings,
    }


# --------------------------------------------------------------------- #
# Listing parsing (v0.7 link-discovery)
# --------------------------------------------------------------------- #

#: The arXiv listing shape, declared rather than pattern-matched.
#:
#: One logical entry spans TWO sibling elements — `<dt>` carries the abs link,
#: `<dd>` the title and authors — which is what `pair_with` exists for.
#:
#: This replaced three regexes that returned ZERO entries against a live page
#: holding 47 (measured 2026-07-28). They required double-quoted attributes and
#: `href="`; arXiv serves single quotes and `<a href ="…">`. A DOM parse is
#: indifferent to quote style, attribute order and whitespace inside tags —
#: none of which are part of the page's meaning. A *tolerant* regex was the
#: obvious fix and was rejected: it survives this change and dies on the next.
_LISTING_SCHEMA = Schema(
    container="dl#articles",
    row="dt",
    pair_with="dd",
    fields={
        "id": DomField(css="a[title='Abstract']", attr="href", required=True),
        "title": DomField(css="div.list-title", strip_prefix="Title:", required=True),
        "authors": DomField(css="div.list-authors", strip_prefix="Authors:"),
    },
)


def _parse_listing(html: str) -> Extraction:
    """Extract the listing entries, carrying WHY when there are none.

    Returns the `Extraction` rather than a bare list so the caller can tell a
    genuinely empty listing (`EMPTY` — a fact about the page) from selectors
    that stopped matching (`ROT` — a fact about this schema). Collapsing the two
    into `[]` is how the old parser reported "0 papers" with `Verdict.ok` for
    however long it had been broken.
    """
    got = extract(html, _LISTING_SCHEMA)
    return Extraction(
        verdict=got.verdict,
        rows=tuple({**row, "id": row["id"].rsplit("/", 1)[-1]} for row in got.rows),
        missing=got.missing,
    )


def _render_listing(
    cat: str,
    window: str,
    entries: tuple[dict[str, str], ...],
    *,
    advertised_total: int | None = None,
) -> dict[str, object]:
    """Render an arxiv listing as a terse list.

    `advertised_total` is the count the PAGE states ("Total of 408 entries"),
    which is routinely far larger than what one request renders. It belongs in
    the markdown because the caller of `query` never sees the body: given only
    `## Papers (25)`, a model correctly concludes it has 25 papers and wrongly
    concludes that is all of them. Measured on the 2026-07-28 bench run, where
    a2web answered "you are seeing all 25" about a 445-entry listing and scored
    1 and 2 against WebFetch's 5.

    Sourced from `listing_oracle`, not a local regex: `handlers/` may not carry
    markup regexes (the markup-funnel guard), and advertised totals are exactly
    what that module already owns.
    """
    shown = min(len(entries), _LISTING_RENDER_CAP)
    title_text = f"arXiv · {cat} · {window}"
    # Only a total that EXCEEDS what we render is news. An equal or smaller one
    # (a short listing, or an oracle that matched some other number on the page)
    # would turn "25 of 25" into noise, or worse, into a false shortfall.
    if advertised_total is not None and advertised_total > shown:
        count_label = f"Papers ({shown} of {advertised_total})"
        preamble = f"_Showing {shown} of {advertised_total} entries the page advertises — this is a partial view._\n"
    else:
        count_label = f"Papers ({shown})"
        preamble = ""
    parts: list[str] = [f"# {title_text}\n", f"## {count_label}\n"]
    if preamble:
        parts.append(preamble)
    for entry in entries[:_LISTING_RENDER_CAP]:
        parts.append(f"- **{entry['title']}** ({entry['authors']})\n  <https://arxiv.org/abs/{entry['id']}>")
    headings: list[Heading] = [
        Heading(level=1, text=title_text),
        Heading(level=2, text=count_label),
    ]
    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title_text,
        "byline": None,
        "headings": headings,
    }


def _listing_candidates(entries: tuple[dict[str, str], ...]) -> list[NextLink]:
    """Build up to 10 NextLink entries from listing entries.

    `reason` is the comma-joined first authors (truncated to the model's 80-char cap).
    """
    out: list[NextLink] = []
    for entry in entries[:10]:
        out.append(
            NextLink(
                anchor=entry["title"],
                url=f"https://arxiv.org/abs/{entry['id']}",
                reason=entry["authors"] or "abstract",
                kind="drilldown",
            ),
        )
    return out
