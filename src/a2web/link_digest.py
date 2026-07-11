"""Link digest — let the extractor see a page's real anchors and hand one back safely.

The extractor is fed page prose + JSON-LD, but trafilatura strips hrefs, so the
model never sees the page's link graph and would *guess* a sub-resource URL
(the originating Hepsiburada reviews miss — a `-yorumlari` page it could not
return). This module closes that hole with three pure steps (no I/O, no async):

1. :func:`build_digest` — turn the selectolax ``links[]`` (already flowing to
   ``fc.links``) into a compact, deduped digest of ``{{n}}`` handles. Safe
   deterministic cuts only (self / fragment / ``javascript:`` / dup); **no
   relevance filtering** — the extractor judges relevance (ADR-0012 neutrality).
2. :meth:`LinkDigest.render` — the digest text appended to the extractor menu
   *tail* (so the cache prefix stays byte-stable).
3. :meth:`LinkDigest.rehydrate_handle` / :meth:`LinkDigest.rehydrate_text` —
   closed-set: the model emits ``{{3}}``, the server supplies the real href.
   A handle absent from the table is dropped, never emitted. Matching is on the
   exact ``{{n}}`` delimiter form, so identifier-like substrings inside product
   names / SKUs ("Xiaomi L1", "WH-L7", "HBCV0000ATJ8M2") are never corrupted —
   the collision failure that bare ``L1`` handles suffered (design D2).

Domain-coupled (reads :class:`a2web.models.Link`); stays out of ``packages/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .models import Link

# Exact delimited handle — the ONLY form rehydration matches. Bare `L1` / `[L1]`
# were rejected in design D2 (collide with SKUs / markdown); `{{n}}` is ASCII,
# markdown-safe, and does not occur in real anchor text.
_HANDLE_RE = re.compile(r"\{\{(\d+)\}\}")

# Contact schemes: the href value IS the datum (the email / phone), so it is
# surfaced raw rather than as a fetchable drilldown (design D4).
_CONTACT_SCHEMES = ("mailto:", "tel:")

# Schemes that are never a fetchable resource — cut before encoding (design D3).
_UNFETCHABLE_SCHEMES = ("javascript:", "data:", "blob:", "about:")


@dataclass(slots=True, frozen=True)
class LinkAffordance:
    """One deduped link the extractor may reference by its ``{{handle}}``.

    ``labels`` is the union of distinct anchor texts that pointed at ``href``
    (design D5 — merge by target, keep every label). ``off_domain`` flags a
    target on a different registrable domain than the page: its anchor text is
    attacker-controllable, so the caller treats it with caution (design D11).
    ``is_contact`` marks ``mailto:`` / ``tel:`` — surfaced as a raw value, not a
    drilldown.
    """

    handle: int
    labels: tuple[str, ...]
    href: str
    off_domain: bool
    is_contact: bool = False


@dataclass(slots=True, frozen=True)
class LinkDigest:
    """The assembled digest: encoded text for the menu + a closed rehydration set."""

    entries: tuple[LinkAffordance, ...]

    def __bool__(self) -> bool:
        return bool(self.entries)

    def table(self) -> dict[int, str]:
        """Handle → real href. The closed set; nothing else may be rehydrated."""
        return {e.handle: e.href for e in self.entries}

    def render(self) -> str:
        """The digest block appended to the extractor menu tail.

        One line per entry: ``{{n}} <labels> · <trimmed path>`` (domain shown
        only when off-domain, since a same-domain path needs no disambiguation
        and the domain would just cost tokens — design D2).
        """
        lines = [_render_affordance(e) for e in self.entries]
        return "## page links\n\n" + "\n".join(lines)

    def rehydrate_handle(self, handle: int) -> str | None:
        """Real href for a handle, or ``None`` when the handle is not in the set."""
        return self.table().get(handle)

    def rehydrate_text(self, text: str) -> str:
        """Replace exact ``{{n}}`` tokens in prose with their real href.

        Known handles → href; unknown handles → removed (never leaked). Only the
        delimited form is touched, so identifier-like substrings in the prose are
        left intact.
        """
        table = self.table()

        def _sub(m: re.Match[str]) -> str:
            return table.get(int(m.group(1)), "")

        return _HANDLE_RE.sub(_sub, text)


def build_digest(links: list[Link], *, page_url: str, limit: int | None = None) -> LinkDigest:
    """Assemble a :class:`LinkDigest` from a page's anchors.

    Safe deterministic cuts only (self / fragment-only / unfetchable-scheme /
    empty / exact-dup); dedup by resolved target with label union; assign
    stable ``{{1}}..{{n}}`` handles in first-seen order. Pure.

    ``limit`` caps the number of distinct targets encoded (a server-side circuit
    breaker on token cost — first-seen order, so page-leading links win). This
    is a hard ceiling, never surfaced to the model as a target; relevance is the
    model's job (ADR-0012). ``None`` means no cap.
    """
    base_reg = _registrable_domain(page_url)
    # Preserve first-seen order for stable handles; merge labels per target.
    order: list[str] = []
    labels_by_target: dict[str, list[str]] = {}
    href_by_target: dict[str, str] = {}
    contact_targets: set[str] = set()

    for link in links:
        resolved = _resolve(link.href, page_url)
        if resolved is None:
            continue  # cut: empty / fragment-only / unfetchable / self
        target_key, href, is_contact = resolved
        if target_key not in labels_by_target:
            order.append(target_key)
            labels_by_target[target_key] = []
            href_by_target[target_key] = href
            if is_contact:
                contact_targets.add(target_key)
        label = link.anchor.strip()
        if label and label not in labels_by_target[target_key]:
            labels_by_target[target_key].append(label)

    if limit is not None and limit >= 0:
        order = order[:limit]
    entries: list[LinkAffordance] = []
    for handle, target_key in enumerate(order, start=1):
        href = href_by_target[target_key]
        is_contact = target_key in contact_targets
        off_domain = (not is_contact) and _registrable_domain(href) != base_reg
        entries.append(
            LinkAffordance(
                handle=handle,
                labels=tuple(labels_by_target[target_key]),
                href=href,
                off_domain=off_domain,
                is_contact=is_contact,
            )
        )
    return LinkDigest(entries=tuple(entries))


def _resolve(href: str, page_url: str) -> tuple[str, str, bool] | None:
    """Normalize one href → ``(dedup_key, absolute_href, is_contact)`` or ``None``.

    ``None`` means the link is safe-cut: empty, a bare fragment, an unfetchable
    scheme, or the page itself. Contact links (``mailto:`` / ``tel:``) pass
    through verbatim as their own dedup key.
    """
    raw = (href or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered.startswith(_CONTACT_SCHEMES):
        return raw, raw, True
    if lowered.startswith(_UNFETCHABLE_SCHEMES):
        return None
    if raw.startswith("#"):
        return None  # fragment-only — same document

    absolute = urljoin(page_url, raw)
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https"):
        return None
    # Dedup / self-link key ignores the fragment: `…/p#reviews` and `…/p` are
    # the same document. Trailing slash normalized so `/x` and `/x/` collapse.
    path = parts.path.rstrip("/") or "/"
    key = f"{parts.scheme}://{parts.netloc}{path}"
    if parts.query:
        key += f"?{parts.query}"
    self_key = _self_key(page_url)
    if key == self_key:
        return None  # self-link
    return key, absolute, False


def _self_key(page_url: str) -> str:
    parts = urlsplit(page_url)
    path = parts.path.rstrip("/") or "/"
    key = f"{parts.scheme}://{parts.netloc}{path}"
    if parts.query:
        key += f"?{parts.query}"
    return key


def _registrable_domain(url: str) -> str:
    """Best-effort eTLD+1 without a PSL dependency (design D11 caution flag).

    Strips a leading ``www.`` and keeps the last two labels. Conservative: it
    over-flags exotic multi-part TLDs as different, which is the safe direction
    for a caution flag. Contact/relative inputs return ``""``.
    """
    host = (urlsplit(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    return ".".join(labels[-2:])


def _render_affordance(entry: LinkAffordance) -> str:
    label = " / ".join(entry.labels) if entry.labels else "(no label)"
    if entry.is_contact:
        return f"{{{{{entry.handle}}}}} {label} · {entry.href}"
    parts = urlsplit(entry.href)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    if entry.off_domain:
        return f"{{{{{entry.handle}}}}} {label} · {parts.netloc}{path}"
    return f"{{{{{entry.handle}}}}} {label} · {path}"


__all__ = ["LinkAffordance", "LinkDigest", "build_digest"]
