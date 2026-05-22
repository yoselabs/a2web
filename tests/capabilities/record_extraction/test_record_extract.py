"""record_extract — structural detection of repeated listing records."""

from __future__ import annotations

from a2web.packages.record_extract import extract_records


def _repo_card(owner: str, name: str, desc: str) -> str:
    return (
        '<article class="Box-row">'
        f'<a href="/login?return_to=%2F{owner}%2F{name}">Star</a>'
        f'<h2 class="h3"><a href="/{owner}/{name}">{owner} / {name}</a></h2>'
        f"<p>{desc}</p>"
        "</article>"
    )


_GH_HTML = (
    "<html><body>"
    '<ul class="MarketingNavigation">'
    + "".join(
        f'<li><a href="/features/{x}">{x} — write better code with AI assistance today</a></li>'
        for x in ("copilot", "actions", "codespaces", "security", "issues", "discussions", "sponsors")
    )
    + "</ul>"
    '<div class="Box">'
    + "".join(
        _repo_card(f"owner{i}", f"repo{i}", f"A description of repository number {i} explaining what it does in detail")
        for i in range(8)
    )
    + "</div>"
    "</body></html>"
)

_FLAT_LIST = (
    "<html><body><ul>"
    + "".join(f'<li><a href="/post/{i}">Blog post number {i} about an interesting topic</a></li>' for i in range(20))
    + "</ul></body></html>"
)

_ARTICLE = (
    "<html><body><nav>Home About Contact</nav>"
    "<article><h1>A Single Article</h1>"
    + "".join(f"<p>Paragraph {i} of ordinary article prose with no links at all here.</p>" for i in range(8))
    + "</article><footer>Privacy Terms</footer></body></html>"
)

_SHELL = '<html><body><div id="root"></div><script>window.__APP__={}</script></body></html>'


def test_repo_card_cluster_beats_marketing_nav() -> None:
    rs = extract_records(_GH_HTML)
    assert rs is not None
    assert len(rs.records) == 8
    assert "article" in rs.child_signature and "Box-row" in rs.child_signature


def test_flat_link_list_is_located() -> None:
    rs = extract_records(_FLAT_LIST)
    assert rs is not None
    assert len(rs.records) == 20
    assert rs.child_signature.startswith("li")


def test_article_page_yields_no_region() -> None:
    assert extract_records(_ARTICLE) is None


def test_near_empty_shell_yields_no_region() -> None:
    assert extract_records(_SHELL) is None


def test_each_record_keeps_slug_text_and_all_links() -> None:
    rs = extract_records(_GH_HTML)
    assert rs is not None
    first = rs.records[0]
    assert "owner0 / repo0" in first.markdown
    hrefs = {href for _, href in first.links}
    # both the chrome action link and the content link are retained
    assert any("/login" in h for h in hrefs)
    assert any(h.endswith("/owner0/repo0") for h in hrefs)
    assert len(first.links) >= 2


def test_primary_link_is_the_heading_link_not_index_zero() -> None:
    rs = extract_records(_GH_HTML)
    assert rs is not None
    first = rs.records[0]
    assert first.primary_link is not None
    # index-0 link is the Star button; primary must be the heading repo link
    assert first.primary_link[1].endswith("/owner0/repo0")


def test_base_url_resolves_relative_hrefs() -> None:
    rs = extract_records(_GH_HTML, base_url="https://github.com")
    assert rs is not None
    assert rs.records[0].primary_link == ("owner0 / repo0", "https://github.com/owner0/repo0")
