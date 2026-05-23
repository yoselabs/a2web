"""html_fragment converter — `to_markdown` + `to_text` capability tests.

Covers the boundary contract: entity decode, link preserve, nbsp fold,
nested tags, malformed HTML, base_url absolutization, empty input.
"""

from __future__ import annotations

import pytest

from a2web.packages.html_fragment import to_markdown, to_text


class TestEmptyInput:
    def test_empty_string_to_markdown(self) -> None:
        assert to_markdown("") == ""

    def test_whitespace_only_to_markdown(self) -> None:
        assert to_markdown("   \n  ") == ""

    def test_empty_string_to_text(self) -> None:
        assert to_text("") == ""

    def test_whitespace_only_to_text(self) -> None:
        assert to_text("   ") == ""


class TestEntityDecode:
    def test_rsquo_decoded_in_text(self) -> None:
        # The discourse bug — must not surface as `&rsquo;`.
        result = to_text("It&rsquo;s a test")
        assert "&" not in result
        assert "rsquo" not in result
        assert "’" in result  # noqa: RUF001

    def test_rsquo_decoded_in_markdown(self) -> None:
        result = to_markdown("<p>It&rsquo;s fine</p>")
        assert "&rsquo;" not in result
        assert "’" in result  # noqa: RUF001

    def test_amp_decoded(self) -> None:
        assert to_text("AT&amp;T") == "AT&T"

    def test_numeric_entity_decoded(self) -> None:
        assert to_text("&#x27;quoted&#x27;") == "'quoted'"


class TestNbspFold:
    def test_nbsp_entity_folded(self) -> None:
        assert to_text("a&nbsp;b") == "a b"

    def test_nbsp_unicode_folded(self) -> None:
        assert to_text("a\xa0b") == "a b"

    def test_nbsp_in_markdown(self) -> None:
        assert "\xa0" not in to_markdown("<p>a&nbsp;b</p>")


class TestLinkPreservation:
    def test_link_simple(self) -> None:
        assert to_markdown('<a href="https://e.com">click</a>') == "[click](https://e.com)"

    def test_link_inside_paragraph(self) -> None:
        result = to_markdown('<p>before <a href="https://e.com">l</a> after</p>')
        assert result == "before [l](https://e.com) after"

    def test_link_without_href_renders_text(self) -> None:
        assert to_markdown("<a>bare</a>") == "bare"

    def test_base_url_absolutizes(self) -> None:
        result = to_markdown('<a href="/rel">x</a>', base_url="https://e.com/foo/")
        assert result == "[x](https://e.com/rel)"

    def test_no_base_url_keeps_relative(self) -> None:
        result = to_markdown('<a href="/rel">x</a>')
        assert "(/rel)" in result


class TestEmphasis:
    def test_strong(self) -> None:
        assert to_markdown("<p><strong>x</strong></p>") == "**x**"

    def test_b(self) -> None:
        assert to_markdown("<p><b>x</b></p>") == "**x**"

    def test_em(self) -> None:
        assert to_markdown("<p><em>x</em></p>") == "*x*"

    def test_i(self) -> None:
        assert to_markdown("<p><i>x</i></p>") == "*x*"


class TestNestedTags:
    def test_nested_strong_in_paragraph_with_link(self) -> None:
        result = to_markdown('<p><strong>x</strong> <a href="https://e.com">y</a></p>')
        assert "**x**" in result
        assert "[y](https://e.com)" in result


class TestListItems:
    def test_simple_list(self) -> None:
        result = to_markdown("<ul><li>a</li><li>b</li></ul>")
        assert "- a" in result
        assert "- b" in result

    def test_list_with_links(self) -> None:
        result = to_markdown('<ul><li><a href="/x">aa</a></li></ul>')
        assert "- [aa](/x)" in result


class TestParagraphs:
    def test_paragraphs_separated_by_blank_lines(self) -> None:
        result = to_markdown("<p>one</p><p>two</p>")
        assert result == "one\n\ntwo"

    def test_br_becomes_newline(self) -> None:
        assert to_markdown("foo<br>bar") == "foo\nbar"


class TestMalformedHtml:
    def test_unclosed_tag_does_not_raise(self) -> None:
        # Must not raise.
        assert to_markdown("<p>no closing tag <b>bold").strip() != ""

    def test_random_garbage_does_not_raise(self) -> None:
        to_markdown("<<<>>> << <p garbage")
        to_text("<<<>>> <<")


class TestPlainTextDrops:
    def test_other_tags_stripped_in_markdown(self) -> None:
        result = to_markdown("<p><span>kept</span></p>")
        assert "<span>" not in result
        assert "kept" in result

    def test_tags_stripped_in_text(self) -> None:
        assert to_text("<p>a <span>b</span> c</p>") == "a b c"


class TestRealWorldFragments:
    """Smoke tests against shapes lifted from the handlers."""

    def test_discourse_cooked(self) -> None:
        # A Discourse cooked-style fragment.
        html = '<p>Hello <a href="https://example.com">there</a>.</p>'
        result = to_markdown(html)
        assert result == "Hello [there](https://example.com)."

    def test_habr_text_html(self) -> None:
        html = '<div><p>Body with <strong>bold</strong> and <a href="https://e.com/ref">a ref</a>.</p></div>'
        result = to_markdown(html)
        assert "**bold**" in result
        assert "[a ref](https://e.com/ref)" in result

    @pytest.mark.parametrize(
        ("html", "expected_contains"),
        [
            ("<p>Comment <i>note</i></p>", "*note*"),
            ("Plain text only", "Plain text only"),
        ],
    )
    def test_hn_algolia_text(self, html: str, expected_contains: str) -> None:
        assert expected_contains in to_markdown(html)
