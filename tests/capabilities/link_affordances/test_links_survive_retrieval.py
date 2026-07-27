"""A page's anchors survive retrieval, whichever tier served it.

`other_pages` was IMPOSSIBLE to emit on any page not served by the raw tier.
Pre-rendering tiers install `TierResult.pre_rendered: Rendered(...)`, which
carried no links, so `fc.links` stayed empty, `_build_link_digest` bailed, no
`## page links` block reached the prompt, and the prompt then correctly told the
model to omit the field. Measured on `arxiv.org/list/cs.CL/recent` via the
browser tier: 50 arXiv ids in `content_md`, **0 links, 0 headings, 0 markdown
link targets** (`eval/findings_2026-07-28.md`).

Retrieval path is not something the caller chose or can see. Making the index
depend on it means the same URL yields an index or not according to whether an
anti-bot wall happened to force a browser — and it fails hardest on exactly the
pages a caller cannot cheaply fetch twice.

These are offline: a fixture of known shape through each tier's markdown path.
No network, no LLM.
"""

from __future__ import annotations

import re

import pytest

from a2web.tiers.archive import _extract as archive_extract
from a2web.tiers.browser import _extract as browser_extract

_BASE_URL = "https://example.org/list/recent"

#: Anchors the fixture genuinely carries, inside a body long enough that
#: trafilatura treats it as content rather than boilerplate. Short fragments are
#: discarded wholesale, which would make any assertion below vacuous.
_ANCHOR_COUNT = 4

_FIXTURE = """<html><head><title>Recent</title></head><body><article>
<h1>Recent submissions</h1>
<p>This is a deliberately long paragraph of body text so the extractor treats
this block as real article content rather than navigational boilerplate, which
it otherwise discards outright on short fragments — a discard that would make
every assertion in this module pass against an empty string.</p>
<ul>
<li><a href="https://example.org/abs/1001">Attention Is All You Need Again</a> —
a paper about transformers and their many descendants in language processing.</li>
<li><a href="https://example.org/abs/1002">Scaling Laws Revisited</a> —
another paper carrying a reasonably long description of its contents here.</li>
<li><a href="/abs/1003">A Relative Link Worth Absolutising</a> —
a third entry, linked relatively, with enough text to survive extraction.</li>
</ul>
<p>See <a href="https://elsewhere.example.com/index">the full index</a> for the
complete archive, which lives on a different host entirely from this one.</p>
</article></body></html>"""


def _markdown_link_targets(md: str) -> list[str]:
    return re.findall(r"\[[^\]]*\]\((https?://[^)]+)\)", md)


def test_the_fixture_is_link_dense() -> None:
    """Non-vacuity floor for every assertion below.

    Without this, an extractor that returned `""` would satisfy "the links it
    found are correct" trivially, and a fixture silently emptied by an escaping
    slip would read as a passing guard.
    """
    assert _FIXTURE.count("<a href=") == _ANCHOR_COUNT, (
        f"the fixture carries {_FIXTURE.count('<a href=')} anchors, expected {_ANCHOR_COUNT}. "
        "Fix the fixture or the constant — do not weaken the assertions that depend on it."
    )


@pytest.mark.parametrize(
    "extract",
    [
        pytest.param(browser_extract, id="browser"),
        pytest.param(archive_extract, id="archive"),
    ],
)
@pytest.mark.asyncio
async def test_pre_rendered_markdown_keeps_link_targets(extract) -> None:
    """A page whose substance IS its links must not render as target-less prose."""
    extracted = await extract(_FIXTURE, _BASE_URL)
    md = extracted.content_md

    assert md.strip(), "the extractor returned nothing for a content-shaped fixture"
    targets = _markdown_link_targets(md)
    assert len(targets) >= _ANCHOR_COUNT - 1, (
        f"pre-rendered markdown carries {len(targets)} link target(s) for a fixture with "
        f"{_ANCHOR_COUNT} anchors. A listing rendered without its targets is prose that "
        f"mentions links, which no downstream consumer can act on.\n\n{md}"
    )
    assert len(extracted.links) >= _ANCHOR_COUNT - 1, (
        f"the tier extracted {len(extracted.links)} link(s) for a fixture with "
        f"{_ANCHOR_COUNT} anchors — nothing to carry across the pre-rendered seam."
    )


def test_the_canonical_extractor_returns_the_links() -> None:
    """The shelf extractor yields links from the same parse as the markdown.

    This is the capability the six direct `trafilatura.extract` callers were
    discarding — not a missing feature, a bypassed one.
    """
    import asyncio

    from content_extract import extract_markdown

    extracted = asyncio.run(extract_markdown(_FIXTURE, _BASE_URL, include_links=True))

    assert len(extracted.links) >= _ANCHOR_COUNT - 1, (
        f"the canonical extractor returned {len(extracted.links)} link(s) for a fixture "
        f"with {_ANCHOR_COUNT} anchors. If this fails the premise of the whole change is "
        "wrong — the shelf extractor is not the answer and the design needs revisiting."
    )
    # Hrefs arrive as authored. Absolutisation belongs to `link_digest._resolve`
    # (`urljoin(page_url, raw)`), not to extraction — asserting it here would
    # pin the wrong layer and would break the moment the digest did its job.
    hrefs = {lk.href for lk in extracted.links}
    assert "/abs/1003" in hrefs, f"the relative anchor was dropped entirely. hrefs={sorted(hrefs)}"
    assert "https://elsewhere.example.com/index" in hrefs, (
        f"the off-domain anchor was dropped. Off-domain candidates are ADR-0014's concern "
        f"and must reach the digest to be judged there. hrefs={sorted(hrefs)}"
    )


def test_rendered_carries_links_across_the_pre_rendered_seam() -> None:
    """`Rendered` must be able to carry what the producer extracted.

    Without a field here, a tier that correctly extracts links still drops them
    at the seam — which is the shape of the original defect, one layer in.
    """
    import dataclasses

    from a2web.tiers import Rendered

    fields = {f.name for f in dataclasses.fields(Rendered)}
    assert "links" in fields, (
        f"Rendered carries {sorted(fields)} — no `links`. A pre-rendering tier has nowhere "
        "to put the anchors it extracted, so they are dropped at the seam and the link "
        "digest is never built."
    )
