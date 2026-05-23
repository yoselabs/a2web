"""record_extract — tree-aware structural detection of repeated records.

Covers flat catalogs (depth 0), threaded discussions (depth > 0, own-scope —
no double-counting), and the three detection guards: non-empty class token,
parent-signature consistency, and heading presence.
"""

from __future__ import annotations

from a2web.packages.record_extract import extract_records


def _repo_card(i: int) -> str:
    return (
        '<article class="Box-row">'
        f'<a href="/login?return_to=%2Fowner{i}%2Frepo{i}">Star</a>'
        f'<h2 class="h3"><a href="/owner{i}/repo{i}">owner{i} / repo{i}</a></h2>'
        f"<p>A description of repository number {i} explaining what it does.</p>"
        "</article>"
    )


# A flat catalog — 8 repeated heading-bearing cards, plus a classless marketing
# nav whose `<li>` signature has an empty class token (guard (a) rejects it).
_FLAT_LISTING = (
    "<html><body>"
    '<ul class="MarketingNavigation">'
    + "".join(
        f'<li><a href="/features/{x}">{x} — build better software with help</a></li>'
        for x in ("copilot", "actions", "codespaces", "security", "issues", "sponsors")
    )
    + "</ul>"
    '<div class="Box">'
    + "".join(_repo_card(i) for i in range(8))
    + "</div>"
    "</body></html>"
)


def _comment(i: int, body: str, replies: str = "") -> str:
    return (
        '<li class="comment">'
        f'<h4 class="byline"><a href="/u/user{i}">user{i}</a></h4>'
        f'<div class="comment_text">{body}</div>'
        f'<ol class="comments">{replies}</ol>'
        "</li>"
    )


# A threaded discussion — 3 top-level comments, each with one nested reply.
_THREAD = (
    '<html><body><ol class="comments">'
    + _comment(
        0,
        "Top comment zero with a real sentence of discussion text here.",
        _comment(10, "A reply to comment zero that also says something substantive."),
    )
    + _comment(
        1,
        "Top comment one offering an opinion about the topic at some length.",
        _comment(11, "A reply to comment one continuing the thread with more words."),
    )
    + _comment(
        2,
        "Top comment two raising a separate point worth a few words of text.",
        _comment(12, "A reply to comment two wrapping up the discussion nicely here."),
    )
    + "</ol></body></html>"
)

# A reference doc — repeated heading-bearing `<section>` with an empty class.
_REFERENCE_DOC = (
    "<html><body><article>"
    + "".join(
        f"<section><h2>Section {i}</h2>"
        f'<p>Reference text for section {i} with a <a href="/api/{i}">symbol link</a> here.</p>'
        "</section>"
        for i in range(6)
    )
    + "</article></body></html>"
)

# Scattered page chrome — 8 `div.menu-item`, each under a uniquely-classed
# parent, so the records share no dominant parent signature.
_SCATTERED_CHROME = (
    "<html><body>"
    + "".join(
        f'<div class="col-{i}">'
        f'<div class="menu-item"><h3>Menu {i}</h3>'
        f'<a href="/go/{i}">navigate to section {i} of the site here</a></div>'
        "</div>"
        for i in range(8)
    )
    + "</body></html>"
)

# Article prose — repeated classed `<p>` runs with inline links but no heading.
_ARTICLE_PROSE = (
    "<html><body><article><h1>The Article Title</h1>"
    + "".join(
        f'<p class="para">Paragraph {i} of ordinary article prose that mentions '
        f'<a href="/ref/{i}">a reference</a> and continues for a while longer.</p>'
        for i in range(8)
    )
    + "</article></body></html>"
)

_SHELL = '<html><body><div id="root"></div><script>window.__APP__={}</script></body></html>'


def test_flat_listing_is_located_at_depth_zero() -> None:
    rs = extract_records(_FLAT_LISTING)
    assert rs is not None
    assert len(rs.records) == 8
    assert "article" in rs.child_signature and "Box-row" in rs.child_signature
    assert all(r.depth == 0 for r in rs.records)
    assert rs.max_depth == 0
    assert rs.is_threaded is False


def test_threaded_discussion_carries_depth() -> None:
    rs = extract_records(_THREAD)
    assert rs is not None
    assert len(rs.records) == 6
    assert rs.is_threaded is True
    assert rs.max_depth == 1
    # document order: a top comment (depth 0) is immediately followed by its reply (depth 1)
    assert rs.records[0].depth == 0
    assert rs.records[1].depth == 1


def test_threaded_record_text_is_own_scope_no_double_counting() -> None:
    rs = extract_records(_THREAD)
    assert rs is not None
    top, reply = rs.records[0], rs.records[1]
    assert "Top comment zero" in top.text
    # the reply's text must NOT be folded into its parent comment
    assert "reply to comment zero" not in top.text
    assert "reply to comment zero" in reply.text


def test_reference_doc_sections_are_rejected() -> None:
    """Repeated heading-bearing `<section>` with an empty class — guard (a)."""
    assert extract_records(_REFERENCE_DOC) is None


def test_scattered_chrome_is_rejected() -> None:
    """Records with no dominant shared parent signature — guard (b)."""
    assert extract_records(_SCATTERED_CHROME) is None


def test_article_prose_paragraphs_are_rejected() -> None:
    """Classed `<p>` runs that mostly lack a heading — guard (c)."""
    assert extract_records(_ARTICLE_PROSE) is None


def test_near_empty_shell_yields_no_region() -> None:
    assert extract_records(_SHELL) is None


def test_each_record_keeps_slug_text_and_all_links() -> None:
    rs = extract_records(_FLAT_LISTING)
    assert rs is not None
    first = rs.records[0]
    assert "owner0 / repo0" in first.markdown
    hrefs = {href for _, href in first.links}
    # both the chrome action link and the content link are retained
    assert any("/login" in h for h in hrefs)
    assert any(h.endswith("/owner0/repo0") for h in hrefs)
    assert len(first.links) >= 2


def test_heading_link_is_the_heading_link_not_index_zero() -> None:
    rs = extract_records(_FLAT_LISTING)
    assert rs is not None
    first = rs.records[0]
    assert first.heading_link is not None
    # index-0 link is the Star button; heading_link must be the heading repo link
    assert first.heading_link[1].endswith("/owner0/repo0")
    # heading_text is populated alongside heading_link when a heading is detected
    assert first.heading_text == "owner0 / repo0"


def test_base_url_resolves_relative_hrefs() -> None:
    rs = extract_records(_FLAT_LISTING, base_url="https://github.com")
    assert rs is not None
    assert rs.records[0].heading_link == ("owner0 / repo0", "https://github.com/owner0/repo0")


def test_record_markdown_leads_with_heading_link_then_body_without_duplication() -> None:
    """A heading-led record renders as `- [title](href)\\n  body\\n  links`,
    and the heading text MUST NOT also appear on the body line."""
    rs = extract_records(_FLAT_LISTING, base_url="https://github.com")
    assert rs is not None
    first = rs.records[0]
    lines = first.markdown.split("\n")
    # First line is the heading link
    assert lines[0] == "- [owner0 / repo0](https://github.com/owner0/repo0)"
    # The heading_text must not appear again on any body line (no duplicate smush)
    body_lines = lines[1:]
    body_blob = " ".join(body_lines)
    assert "owner0 / repo0" not in body_blob


def test_to_markdown_labels_flat_vs_threaded() -> None:
    flat = extract_records(_FLAT_LISTING)
    threaded = extract_records(_THREAD)
    assert flat is not None and threaded is not None
    assert flat.to_markdown().startswith("### Listing (8 records)")
    assert threaded.to_markdown().startswith("### Discussion (6 comments)")
