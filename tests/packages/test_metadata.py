"""Metadata parsing — OG, Twitter, JSON-LD."""

from __future__ import annotations

from a2web.packages.content_extract import parse_metadata
from tests.fixtures import FIXTURES_DIR

_FIXTURE = FIXTURES_DIR / "blog.html"


def test_og_extraction() -> None:
    html = _FIXTURE.read_text()
    meta = parse_metadata(html)
    assert meta["og.type"] == "article"
    assert meta["og.image"] == "https://example.org/cover.jpg"
    assert meta["og.title"].startswith("How adaptive web fetching")


def test_twitter_extraction() -> None:
    html = _FIXTURE.read_text()
    meta = parse_metadata(html)
    assert meta["twitter.card"] == "summary_large_image"
    assert meta["twitter.site"] == "@example"


def test_jsonld_extraction() -> None:
    html = _FIXTURE.read_text()
    meta = parse_metadata(html)
    assert meta["jsonld[0].@type"] == "Article"
    assert meta["jsonld[0].datePublished"] == "2026-04-01T09:00:00Z"


def test_no_metadata_returns_empty_dict() -> None:
    meta = parse_metadata("<html><body><p>plain</p></body></html>")
    assert meta == {}


def test_malformed_jsonld_is_swallowed() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">{ this is not json</script>
    </head><body></body></html>
    """
    meta = parse_metadata(html)
    assert all(not k.startswith("jsonld[") for k in meta)
