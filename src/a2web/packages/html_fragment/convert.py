"""HTML fragment → markdown / plain text.

Boundary contract:
- `to_markdown(html, *, base_url=None)`: paragraphs / line breaks / list items /
  emphasis / `<a href>` preserved as markdown; other tags stripped; entities
  decoded; `\\xa0` folded to space; when `base_url` is provided, relative hrefs
  are resolved absolute.
- `to_text(html)`: tags stripped, entities decoded, `\\xa0` folded to space,
  whitespace collapsed. Use for inline titles / bylines.
- Empty / whitespace-only input → `""`.
- Malformed HTML never raises — lxml's permissive parser tolerates it.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import lxml.html

_NBSP_RE = re.compile("[\xa0\u202f]")
_WS_COLLAPSE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")


def to_text(html: str) -> str:
    """Strip tags, decode entities, fold nbsp. Collapse internal whitespace."""
    if not html or not html.strip():
        return ""
    # lxml's fragment parser tolerates malformed input.
    root = lxml.html.fragment_fromstring(html, create_parent="div")
    text = root.text_content()
    text = unescape(text)
    text = _NBSP_RE.sub(" ", text)
    text = _WS_COLLAPSE_RE.sub(" ", text)
    return text.strip()


def to_markdown(html: str, *, base_url: str | None = None) -> str:
    """Convert an HTML fragment to markdown.

    Preserves: paragraphs (blank-line-separated), `<br>` (single newline),
    `<li>` (leading `- `), `<em>`/`<i>` → `*…*`, `<strong>`/`<b>` → `**…**`,
    `<a href>` → `[text](href)` (absolutized against `base_url` when given).
    Drops all other tags; decodes entities; folds nbsp.
    """
    if not html or not html.strip():
        return ""
    root = lxml.html.fragment_fromstring(html, create_parent="div")
    out: list[str] = []
    _render(root, out, base_url=base_url, inside_block=False)
    text = "".join(out)
    text = unescape(text)
    text = _NBSP_RE.sub(" ", text)
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


# Tags that act as block-level paragraph separators.
_BLOCK_TAGS = frozenset(
    {"p", "div", "section", "article", "header", "footer", "aside", "blockquote", "pre"}
)
# Heading tags — block-level; we keep their text and surround with blank lines.
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def _render(el: lxml.html.HtmlElement, out: list[str], *, base_url: str | None, inside_block: bool) -> None:
    tag = (el.tag or "").lower() if isinstance(el.tag, str) else ""

    if tag == "br":
        out.append("\n")
        if el.tail:
            out.append(el.tail)
        return

    if tag == "li":
        out.append("\n- ")
        _render_text_and_children(el, out, base_url=base_url, inside_block=True)
        out.append("\n")
        if el.tail:
            out.append(el.tail)
        return

    if tag in {"em", "i"}:
        out.append("*")
        _render_text_and_children(el, out, base_url=base_url, inside_block=inside_block)
        out.append("*")
        if el.tail:
            out.append(el.tail)
        return

    if tag in {"strong", "b"}:
        out.append("**")
        _render_text_and_children(el, out, base_url=base_url, inside_block=inside_block)
        out.append("**")
        if el.tail:
            out.append(el.tail)
        return

    if tag == "a":
        href = el.get("href") or ""
        if base_url and href:
            href = urljoin(base_url, href)
        # Collect inner text/markup for the link label.
        inner: list[str] = []
        _render_text_and_children(el, inner, base_url=base_url, inside_block=True)
        label = "".join(inner).strip()
        if href:
            out.append(f"[{label}]({href})")
        else:
            out.append(label)
        if el.tail:
            out.append(el.tail)
        return

    # Block tags (including the synthetic root <div>) and headings get blank-line surrounds.
    is_block = tag in _BLOCK_TAGS or tag in _HEADING_TAGS
    if is_block and inside_block is False and out and not "".join(out).endswith("\n\n"):
        # Only insert separators when not at the very start.
        if "".join(out):
            out.append("\n\n")

    _render_text_and_children(el, out, base_url=base_url, inside_block=inside_block or is_block)

    if is_block:
        out.append("\n\n")

    if el.tail:
        out.append(el.tail)


def _render_text_and_children(
    el: lxml.html.HtmlElement, out: list[str], *, base_url: str | None, inside_block: bool
) -> None:
    if el.text:
        out.append(el.text)
    _render_children(el, out, base_url=base_url, inside_block=inside_block)


def _render_children(
    el: lxml.html.HtmlElement, out: list[str], *, base_url: str | None, inside_block: bool
) -> None:
    for child in el:
        _render(child, out, base_url=base_url, inside_block=inside_block)
