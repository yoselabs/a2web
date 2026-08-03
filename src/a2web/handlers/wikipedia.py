"""Wikipedia handler — Parsoid REST API for clean article HTML.

Match: `<lang>.wikipedia.org/wiki/<title>`. REST API returns HTML that
trafilatura handles cleanly — much smaller than the live page (no nav,
sidebar, edit links, or interaction surface).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

from content_extract import extract_markdown
from dom_schema import Field as DomField
from dom_schema import Schema, extract
from http_fetch import fetch_bytes

from ..models import NEXT_LINKS_CAP, Heading, Link, NextLink, Verdict
from ._common import challenge_verdict, empty_result, map_non_ok, report_rot

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_WIKI_HOST_RE = re.compile(r"^([a-z]{2,3})\.wikipedia\.org$", re.IGNORECASE)
_WIKI_PATH_RE = re.compile(r"^/wiki/([^?#]+)$")
_TIMEOUT_S = 10.0


def _parse(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host_match = _WIKI_HOST_RE.match(parsed.hostname or "")
    if host_match is None:
        return None
    path_match = _WIKI_PATH_RE.match(parsed.path or "")
    if path_match is None:
        return None
    return host_match.group(1).lower(), path_match.group(1)


class WikipediaHandler:
    """Tier-0 handler for Wikipedia article URLs."""

    name: str = "site_handler:wikipedia"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _parse(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import TierResult

        parsed = _parse(url)
        if parsed is None:
            return empty_result(url, Verdict.not_found)
        lang, slug = parsed

        api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{slug}"
        outcome = await fetch_bytes(
            api_url,
            headers={"User-Agent": state.settings.default_ua, "Accept": "text/html"},
            timeout_s=state.settings.request_timeout(_TIMEOUT_S),
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            return non_ok

        html = outcome.body.decode("utf-8", errors="replace")
        if not html:
            return empty_result(url, Verdict.length_floor)

        title = unquote(slug).replace("_", " ")
        # Canonical extractor (NOT a bare trafilatura.extract) — returns links
        # and headings from the same parse, so the pre-rendered payload below can
        # carry them across the seam. See test_trafilatura_funnel.py.
        extracted = await extract_markdown(html, url)
        markdown = extracted.content_md

        if not markdown:
            return empty_result(url, Verdict.length_floor)

        # No wikipedia REST response has ever been observed carrying a challenge.
        # This is SYMMETRY, not an incident fix: the check belongs on every
        # handler that extracts HTML, because one present only where a defect was
        # already observed is one nobody remembers to add to the next handler.
        #
        # It runs AFTER extraction, and this article is exactly why: a first cut
        # checked the raw HTML with an empty `content_md`, and the live probe
        # came back `block_page_detected` on /wiki/Python_(programming_language)
        # because a cited PEP title contains "Network Security". See
        # `challenge_verdict`.
        walled = challenge_verdict(html, content_md=markdown)
        if walled is not None:
            return empty_result(url, walled)

        from ..tiers import Rendered

        next_links = _wikilink_candidates(html, lang=lang)

        return TierResult(
            body=outcome.body,
            content_type="text/html",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered(
                content_md=markdown,
                title=title,
                headings=[Heading(level=h.level, text=h.text) for h in extracted.headings],
                links=[Link(anchor=lk.anchor, href=lk.href, role=lk.role) for lk in extracted.links],
            ),
            next_links=next_links,
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# Wikilink extraction (v0.7 link-discovery)
# --------------------------------------------------------------------- #

#: Parsoid's internal-article-link shape, declared rather than pattern-matched.
#:
#: The container is the document body because wikilinks are scattered through
#: prose — there is no listing region to scope to. But it is `body`
#: **qualified by a class**, and the qualifier is what buys back half the
#: verdict: Parsoid's REST output makes the body itself the parser output
#: (`class="… mw-parser-output parsoid-body"`), which the ordinary rendered
#: article page does NOT — there `mw-parser-output` sits on an inner `div`.
#: Measured on both shapes, 2026-08-02.
#:
#: So the two failures are now separable in the way each can be:
#:
#: - **fed a document that is not Parsoid REST output** — a redirect, an error
#:   page, a REST shape change — the container misses and the verdict is `ROT`,
#:   a fact about this schema. A bare `body` container would have called that
#:   `EMPTY`, blaming the page.
#: - **a rotted ROW selector** — `EMPTY`, and INHERENTLY so: "an article with no
#:   wikilinks" is a legitimate page state, so no verdict can distinguish it.
#:   That half is guarded by the captured-density floor in
#:   `test_wikipedia_captured_page_is_link_dense_enough_to_exercise_the_cap`
#:   and by the probe's `min_candidates`, which is why neither may be zeroed.
#:
#: Note which half the 2026-07-28 incident was: the ROW half. Tightening the
#: container does not catch that class, and claiming it does would be the same
#: error as the guard this docstring used to disclaim.
#:
#: This replaced a regex requiring `href="/wiki/X"` that returned ZERO links
#: against a live article carrying 1066 (measured 2026-07-28). Parsoid serves
#: `rel="mw:WikiLink"` with a RELATIVE `./Target` href; the old docstring
#: asserted the absolute form as fact, and its three tests were green against a
#: hand-written fixture in that same stale shape.
_WIKILINK_SCHEMA = Schema(
    container="body.mw-parser-output",
    row="a[rel='mw:WikiLink']",
    fields={
        "target": DomField(css=".", attr="href", required=True),
        "anchor": DomField(css="."),
    },
)


def _wikilink_candidates(html: str, *, lang: str) -> list[NextLink]:
    """Pull up to `NEXT_LINKS_CAP` outbound article wikilinks from Parsoid HTML.

    Parsoid marks internal article links with `rel="mw:WikiLink"` and a relative
    `./Target` href. Namespaced links (File:, Category:, Help:, …) carry a `:` in
    the target and are filtered out — we want article-to-article links only.
    Deduplicates on target. External citations live elsewhere and are not in
    scope (deferred per spec).

    On `ROT` the index is dropped and the fetch is NOT failed — unlike arXiv's
    listing, wikilinks are the index, not the content, and the article body
    still rendered. But a rotted index and an article that genuinely links
    nowhere must not look alike to an operator (the same collapse that made a
    rate-limited GitHub comments call read as "no comments"), so the miss is
    logged rather than returned as a bare `[]`.
    """
    parsed = extract(html, _WIKILINK_SCHEMA)
    if parsed.is_rot:
        report_rot("wikipedia", missing=sorted(parsed.missing))
        return []

    seen: set[str] = set()
    out: list[NextLink] = []
    for row in parsed.rows:
        if len(out) >= NEXT_LINKS_CAP:
            break
        target = row["target"].removeprefix("./").split("#")[0]
        anchor = row.get("anchor", "").strip()
        if not target or not anchor or ":" in target or target in seen:
            continue
        seen.add(target)
        out.append(
            NextLink(
                anchor=anchor,
                url=f"https://{lang}.wikipedia.org/wiki/{target}",
                reason="related article",
                kind="related",
            ),
        )
    return out
