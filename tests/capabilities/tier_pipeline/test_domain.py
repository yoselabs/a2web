"""Tests for a2web.domain pure functions.

`rewrite_captcha_host` is the new v0.7 surface — pre-routes Google/Bing
search URLs to DuckDuckGo before tier dispatch. Tests cover the rewrite
rules, query preservation, and the not-a-search-path passthrough.
"""

from __future__ import annotations

import pytest

from a2web.domain import rewrite_captcha_host, strip_reader_prefix

# --------------------------------------------------------------------- #
# Reader-prefix normalization
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("wrapped", "target"),
    [
        ("https://r.jina.ai/https://example.com/x", "https://example.com/x"),
        ("http://r.jina.ai/https://example.com/x", "https://example.com/x"),
        ("r.jina.ai/https://example.com/x", "https://example.com/x"),
        ("https://r.jina.ai/http://plain.example/p", "http://plain.example/p"),
    ],
)
def test_strip_reader_prefix_unwraps_target(wrapped: str, target: str) -> None:
    assert strip_reader_prefix(wrapped) == target


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",  # not wrapped
        "https://r.jina.ai/",  # bare reader host, no inner URL
        "https://r.jina.ai/not-a-url",  # reader path that is not a wrapped http(s) URL
    ],
)
def test_strip_reader_prefix_leaves_non_wrapped_untouched(url: str) -> None:
    assert strip_reader_prefix(url) is None


# --------------------------------------------------------------------- #
# Captcha-host pre-routing
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/search?q=site%3Areddit.com+projector",
        "https://google.com/search?q=projector",
        "https://www.bing.com/search?q=projector",
        "https://bing.com/search?q=projector",
    ],
)
def test_rewrite_captcha_host_routes_to_ddg(url: str) -> None:
    """Each known captcha-host search URL rewrites to DDG HTML."""
    out = rewrite_captcha_host(url)
    assert out is not None
    assert out.startswith("https://duckduckgo.com/html/?q=")


def test_rewrite_preserves_query_with_url_encoding() -> None:
    """The `q` parameter is preserved and re-encoded for DDG."""
    out = rewrite_captcha_host("https://www.google.com/search?q=site%3Areddit.com+projector")
    assert out is not None
    # The exact encoding: `:` → `%3A`, ` ` and `+` both → quoted.
    assert "site%3Areddit.com" in out
    assert "projector" in out


def test_rewrite_drops_tracking_params() -> None:
    """Google-specific params (tbm, start, num, hl) are NOT carried over."""
    out = rewrite_captcha_host("https://www.google.com/search?q=foo&tbm=isch&start=10&hl=en")
    assert out is not None
    assert "tbm" not in out
    assert "start" not in out
    assert "hl" not in out


def test_rewrite_returns_none_for_non_search_path() -> None:
    """Google Maps / Drive / Images don't rewrite — only `/search` does."""
    assert rewrite_captcha_host("https://www.google.com/maps") is None
    assert rewrite_captcha_host("https://www.google.com/drive/folder/abc") is None
    assert rewrite_captcha_host("https://www.google.com/images") is None


def test_rewrite_returns_none_for_unknown_host() -> None:
    """Hosts not in the registry pass through unchanged."""
    assert rewrite_captcha_host("https://duckduckgo.com/html/?q=foo") is None
    assert rewrite_captcha_host("https://example.com/search?q=foo") is None
    assert rewrite_captcha_host("https://kagi.com/search?q=foo") is None


def test_rewrite_returns_none_when_q_is_missing() -> None:
    """Missing `q` parameter — no useful rewrite target."""
    assert rewrite_captcha_host("https://www.google.com/search") is None
    assert rewrite_captcha_host("https://www.google.com/search?tbm=isch") is None


def test_rewrite_returns_none_when_q_is_empty() -> None:
    """Empty `q=` — no rewrite."""
    assert rewrite_captcha_host("https://www.google.com/search?q=") is None


def test_rewrite_handles_trailing_slash_on_search() -> None:
    """`/search/` (trailing slash) matches the same as `/search`."""
    out = rewrite_captcha_host("https://www.google.com/search/?q=foo")
    assert out is not None
    assert "duckduckgo.com" in out
