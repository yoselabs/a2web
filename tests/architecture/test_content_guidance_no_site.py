"""Architectural invariant: content guidance is per-KIND, never per-SITE.

content-aware refinement guidance is safe to distribute across regions ONLY
because the "what matters" table keys off the closed content-kind enums, not
off hosts. A single domain/site token in `KIND_GUIDANCE` would be the exact
per-site scar tissue the constitution bans — and would rot the moment the tool
is pointed at a site the author never saw. This test walks every guidance
string and asserts no site marker leaks in.
"""

from __future__ import annotations

import re

from a2web.content_guidance import KIND_GUIDANCE

# A guidance line describes a content archetype (listing / discussion / …). It
# must never name a concrete source. `.com`/`.org`/… catches domains; the named
# hosts catch the sites a2web actually has handlers for (the tempting leaks).
_SITE_MARKERS = re.compile(
    r"\.(?:com|org|net|io|co|ru|tr)\b|reddit|hepsiburada|amazon|ebay|hacker\s*news|\bhn\b|wikipedia|github|arxiv",
    re.IGNORECASE,
)


def test_kind_guidance_keys_are_lowercase_kind_tokens() -> None:
    # Keys must look like structural_form enum values (a small closed set), not
    # hostnames.
    for key in KIND_GUIDANCE:
        assert key.islower()
        assert "." not in key
        assert "/" not in key


def test_no_site_markers_in_guidance_values() -> None:
    for kind, text in KIND_GUIDANCE.items():
        match = _SITE_MARKERS.search(text)
        assert match is None, f"KIND_GUIDANCE[{kind!r}] leaks a site marker: {match.group(0)!r}"
