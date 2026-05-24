"""Prompt cache prefix byte-stability tests (v0.19).

Guards the contract that providers' cache-key prefix (`system + cache_prefix`)
is byte-identical across calls that differ only in `ask`. This is the sole
compliance mechanism for the claude-agent-sdk path (no marker API; CLI caches
internally given a stable prefix) and the OpenAI auto-prefix-cache path.
"""

from __future__ import annotations

from a2web.packages.llm_extract import (
    EXTRACT_CACHEABLE_V1,
    EXTRACT_WITH_AFFORDANCES_V1,
    WEBFETCH_DEFAULT_V1,
    PromptParts,
)

# A page roomy enough that real extraction would benefit from caching it.
_PAGE = (
    "# Stratos Hiking Boot\n\n"
    "A waterproof leather boot designed for multi-day backpacking. The Stratos "
    "uses a Vibram outsole and a TPU shank for stability on uneven terrain.\n\n"
    "## Specifications\n\n"
    "- Weight: 1.4 kg per pair\n"
    "- Material: full-grain leather, Gore-Tex lining\n"
    "- Sizes: EU 38-48\n"
    "- Price: $189\n\n"
    "Read more: https://example.com/reviews\n"
)


def test_cacheable_template_prefix_is_byte_stable_across_asks() -> None:
    parts1 = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="What is the price?")
    parts2 = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Who wrote this?")
    parts3 = EXTRACT_CACHEABLE_V1.render(
        content=_PAGE,
        ask="A wordy, long-form question that varies substantially in tokenization shape — including punctuation and clauses.",
    )

    # The cacheable prefix is system + cache_prefix. Both MUST be byte-identical
    # across different `ask` values for the cache key to hit.
    assert parts1.system == parts2.system == parts3.system
    assert parts1.cache_prefix == parts2.cache_prefix == parts3.cache_prefix

    # And the tails MUST differ (otherwise the question variation is lost).
    assert parts1.tail != parts2.tail
    assert parts2.tail != parts3.tail
    assert parts1.tail != parts3.tail


def test_cacheable_template_prefix_contains_page_content() -> None:
    """Smoke: the page content lives in cache_prefix, not in tail."""
    parts = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q?")
    assert "Stratos Hiking Boot" in parts.cache_prefix
    assert "Stratos Hiking Boot" not in parts.tail
    assert "Q?" in parts.tail


def test_cacheable_template_system_non_empty() -> None:
    """The rules block lives in system — cacheable across all calls regardless of content."""
    parts = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q?")
    assert parts.system != ""
    assert "125-character" in parts.system  # the quote rule


def test_different_pages_yield_different_cache_prefixes() -> None:
    """Page content is part of the cache key — different pages MUST diverge."""
    parts_a = EXTRACT_CACHEABLE_V1.render(content="Page A content", ask="Q?")
    parts_b = EXTRACT_CACHEABLE_V1.render(content="Page B content", ask="Q?")
    assert parts_a.cache_prefix != parts_b.cache_prefix
    # System stays the same — it's content-independent.
    assert parts_a.system == parts_b.system


def test_legacy_template_renders_to_degenerate_shape() -> None:
    """Non-cacheable templates produce cache_prefix='' and pack everything into tail."""
    parts = WEBFETCH_DEFAULT_V1.render(content=_PAGE, ask="Q?")
    assert parts.cache_prefix == ""
    assert parts.tail != ""
    assert _PAGE.strip() in parts.tail
    assert "Q?" in parts.tail


def test_prompt_parts_is_frozen() -> None:
    """Defensive: callers must not mutate parts in-flight."""
    parts = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q?")
    try:
        parts.system = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("PromptParts must be frozen — assignment should raise")


def test_claude_code_concat_equals_legacy_byte_for_byte() -> None:
    """The claude-agent-sdk path concatenates cache_prefix + tail.

    This concatenation MUST share an identical prefix (cache_prefix length)
    across different `ask` values — that is what the Claude CLI's internal
    caching keys on.
    """
    parts1 = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q1")
    parts2 = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q2-different-shape")

    concat1 = parts1.cache_prefix + parts1.tail
    concat2 = parts2.cache_prefix + parts2.tail
    prefix_len = len(parts1.cache_prefix)

    assert concat1[:prefix_len] == concat2[:prefix_len]
    assert concat1[prefix_len:] != concat2[prefix_len:]


def test_prompt_parts_explicit_construction() -> None:
    """The boundary type is constructible directly (used by tests + Extractor)."""
    p = PromptParts(system="s", cache_prefix="cp", tail="t")
    assert p.system == "s"
    assert p.cache_prefix == "cp"
    assert p.tail == "t"


# v0.20 — affordances-aware template must share cache_prefix byte-equality
# with the base cacheable template (the design decision in
# `openspec/changes/add-affordances-to-ask/design.md` §D1).


def test_affordances_template_cache_prefix_matches_base_template() -> None:
    """The affordances template must reuse EXTRACT_CACHEABLE_V1's cache_prefix
    byte-for-byte. Different prefix = different cache key = lost cache hits."""
    parts_base = EXTRACT_CACHEABLE_V1.render(content=_PAGE, ask="Q?")
    parts_aff = EXTRACT_WITH_AFFORDANCES_V1.render(content=_PAGE, ask="Q?")
    assert parts_base.cache_prefix == parts_aff.cache_prefix


def test_affordances_template_prefix_is_byte_stable_across_asks() -> None:
    parts1 = EXTRACT_WITH_AFFORDANCES_V1.render(content=_PAGE, ask="What is the price?")
    parts2 = EXTRACT_WITH_AFFORDANCES_V1.render(content=_PAGE, ask="Who wrote this?")
    parts3 = EXTRACT_WITH_AFFORDANCES_V1.render(content=_PAGE, ask="A very different question with extra clauses.")
    assert parts1.system == parts2.system == parts3.system
    assert parts1.cache_prefix == parts2.cache_prefix == parts3.cache_prefix
    assert parts1.tail != parts2.tail
    assert parts2.tail != parts3.tail


def test_affordances_template_schema_lives_in_tail_not_prefix() -> None:
    """The JSON-envelope schema example MUST live in the tail; if it leaked
    into cache_prefix the prefix would still be stable but bloated, hurting
    the cache-window math."""
    parts = EXTRACT_WITH_AFFORDANCES_V1.render(content=_PAGE, ask="Q?")
    # The closed page_kind enum + cluster list live in the prompt; both belong
    # in the tail (per-call), not the prefix (cached portion).
    assert "page_kind" not in parts.cache_prefix
    assert "page_kind" in parts.tail
    assert "Cluster A" not in parts.cache_prefix
    assert "Cluster A" in parts.tail
