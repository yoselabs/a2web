"""v0.7 link-discovery — composition rule (four-cell matrix) + suppression flag.

Tests `fetcher_response._compose_next_links` directly: the pure folder that
turns `FetchContext.next_links_{handler,llm,enabled}` into the final wire
list. Hits the four cells of the design doc's composition matrix plus the
tool-param off-switch.
"""

from __future__ import annotations

from datetime import UTC, datetime

from a2web.fetcher import FetchContext
from a2web.fetcher_response import _compose_next_links
from a2web.models import NextLink


def _fc(
    *,
    handler: list[NextLink] | None = None,
    llm: list[NextLink] | None = None,
    enabled: bool = True,
) -> FetchContext:
    return FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="x",
        sqlite=None,
        bypass_cache=False,
        url="https://e.com",
        final_url="https://e.com",
        next_links_handler=handler or [],
        next_links_llm=llm or [],
        next_links_enabled=enabled,
    )


def _nl(anchor: str, url: str, kind: str = "drilldown") -> NextLink:
    return NextLink(anchor=anchor, url=url, reason="r", kind=kind)  # type: ignore[arg-type]


def test_compose_both_empty_returns_empty() -> None:
    """Cell 1: no handler, no LLM → []."""
    fc = _fc()
    assert _compose_next_links(fc) == []


def test_compose_handler_only_returns_handler_list() -> None:
    """Cell 2: handler-only (no ask=) → handler list passes through unchanged."""
    handler = [_nl("a", "https://e.com/a"), _nl("b", "https://e.com/b")]
    fc = _fc(handler=handler)
    assert _compose_next_links(fc) == handler


def test_compose_llm_only_returns_llm_list() -> None:
    """Cell 3: ask= only (no handler) → LLM list."""
    llm = [_nl("x", "https://e.com/x")]
    fc = _fc(llm=llm)
    assert _compose_next_links(fc) == llm


def test_compose_both_present_returns_llm_list() -> None:
    """Cell 4: both present → LLM list (the LLM already re-ranked the handler set)."""
    handler = [_nl("a", "https://e.com/a")]
    llm = [_nl("b", "https://e.com/b")]
    fc = _fc(handler=handler, llm=llm)
    assert _compose_next_links(fc) == llm


def test_compose_cap_at_10_enforced() -> None:
    """A list of 15 candidates trims to exactly 10 at compose time."""
    fifteen = [_nl(f"a{i}", f"https://e.com/{i}") for i in range(15)]
    fc = _fc(handler=fifteen)
    assert len(_compose_next_links(fc)) == 10


def test_compose_suppression_flag_forces_empty() -> None:
    """`next_links_enabled=False` forces empty regardless of populated lists."""
    handler = [_nl("a", "https://e.com/a")]
    llm = [_nl("b", "https://e.com/b")]
    fc = _fc(handler=handler, llm=llm, enabled=False)
    assert _compose_next_links(fc) == []


# --------------------------------------------------------------------- #
# Tier 2 URL-must-be-in-markdown validation (drift detection)
# --------------------------------------------------------------------- #


def test_validate_drops_hallucinated_urls() -> None:
    """LLM-supplied URL absent from markdown AND not in handler_urls → dropped."""
    from a2web.fetcher import _validate_llm_next_links_against_markdown
    from a2web.packages.llm_extract import LlmNextLink

    llm_links = [
        LlmNextLink(anchor="real", url="https://real.example.com/page", reason="r", kind="drilldown"),
        LlmNextLink(anchor="hallucinated", url="https://fake.example.com/imaginary", reason="r", kind="drilldown"),
    ]
    markdown = "Some content with [link](https://real.example.com/page) inline."
    kept, dropped = _validate_llm_next_links_against_markdown(
        llm_links,
        markdown=markdown,
        handler_urls=set(),
    )
    assert len(kept) == 1
    assert kept[0].url == "https://real.example.com/page"
    assert dropped == ["https://fake.example.com/imaginary"]


def test_validate_passes_handler_urls_even_when_not_in_markdown() -> None:
    """Handler-supplied URLs are trusted — exempt from the markdown-presence check."""
    from a2web.fetcher import _validate_llm_next_links_against_markdown
    from a2web.packages.llm_extract import LlmNextLink

    llm_links = [
        LlmNextLink(anchor="from handler", url="https://h.example.com/x", reason="r", kind="drilldown"),
    ]
    markdown = "Content with no inline links."
    kept, dropped = _validate_llm_next_links_against_markdown(
        llm_links,
        markdown=markdown,
        handler_urls={"https://h.example.com/x"},
    )
    assert len(kept) == 1
    assert dropped == []
