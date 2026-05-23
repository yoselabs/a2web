"""Shared HTML-fragment converter — `to_markdown` + `to_text`.

lxml-backed, link-preserving, entity-decoded. Used by handlers that need
to convert a server-supplied HTML fragment (Discourse `cooked`, Habr
`textHtml`, V2EX `content_rendered`, HN Algolia comment text, etc.) into
plain markdown or text. No `a2web.<domain>` imports — pure infra.
"""

from .convert import to_markdown, to_text

__all__ = ["to_markdown", "to_text"]
