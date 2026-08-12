"""Gated sections — detect page content withheld behind an in-page interaction.

ADR-0020 (grounded absence): a2web may not report a page section as absent at
source when the page's own markup asserts the section exists. The Hepsiburada
Q&A tab is the motivating case — `role="tab"` + `aria-controls="QuestionAnswers"`,
the panel mounted in the DOM but empty (only skeleton loaders), with the page's
own `aria-label` stating a count of 4.

Mirrors `link_digest.py`'s shape deliberately: three pure steps (no I/O, no
async), a closed handle set, relevance judged by the extractor, never by this
module (ADR-0012 neutrality — detection here is recall-oriented on purpose; see
the openspec change `flag-interaction-gated-sections/design.md` D2).

1. :func:`detect_gated_sections` — scan the retrieved markup with `selectolax`
   for disclosure controls (`role="tab"` / `<details>`) whose target panel is
   either absent from the DOM or, once `<style>`/`<script>`/`<link>` content is
   excluded, carries no text. Assign stable ``{{1}}..{{n}}`` handles in
   document order.
2. :meth:`GatedSectionDigest.render` — the digest text appended to the
   extractor menu tail, same placement convention as the link digest.
3. :meth:`GatedSectionDigest.resolve` — closed-set: the model returns a handle
   int, the server resolves it to the real `GatedSection` or drops it if
   unknown (a handle absent from the detected set is never fabricated).

Deliberately reads raw HTML, not `content_md`: measured against the real
converters (design.md D1), markdown conversion (trafilatura, the converter on
the `raw` tier) drops a `role="tab"` strip entirely. A tier whose retrieved
body is already markdown with no markup (`jina`, `firecrawl`) yields an empty
digest — declared reduced recall, not compensated by a looser text heuristic
(design.md D4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser, Node

# Structural, not textual (design.md D3). A candidate is a labelled control
# whose target panel is either missing or, once script/style/link noise is
# stripped, empty. Live-captured ground truth (2026-08-12, Hepsiburada): a
# panel that already carries real rendered text (a hidden-but-populated
# "Reviews" tab) correctly falls through this predicate — it is not a gate,
# just an inactive tab.
_NOISE_TAGS = frozenset({"style", "script", "link"})

# Trailing count on the label, e.g. `aria-label=" Soru Cevap 4"` -> ("Soru Cevap", 4).
# The bare-digit form is the REAL captured attribute shape (2026-08-12,
# Hepsiburada); the parenthesized form (`"Reviews (4)"`) is a common sibling
# shape elsewhere, cheap to also accept since a miss here only costs the count
# — the section is still detected and surfaced, just without a number.
_TRAILING_COUNT_RE = re.compile(r"^(?P<label>.*\S)\s+\(?(?P<count>\d+)\)?$")

# Server-side ceiling on digest size — a circuit breaker, never a target
# surfaced to the model (relevance is the model's job). Mirrors
# `link_digest._DIGEST_LINK_CAP`.
_DIGEST_GATE_CAP = 50


@dataclass(slots=True, frozen=True)
class GatedSection:
    """One detected disclosure control whose panel was not retrieved.

    `stated_count` is the SOURCE-stated count read from the control's own
    label (never derived or rounded — AGENTS.md "never declare a truncation
    against a number that cannot differ"). `None` when the label carries no
    trailing count (e.g. a plain "Hepsitaksit" tab with nothing to count).
    """

    handle: int
    label: str
    stated_count: int | None


@dataclass(slots=True, frozen=True)
class GatedSectionDigest:
    """The assembled digest: menu text + a closed handle→section set."""

    entries: tuple[GatedSection, ...]

    def __bool__(self) -> bool:
        return bool(self.entries)

    def render(self) -> str:
        """The digest block appended to the extractor menu tail.

        One line per entry: ``{{n}} <label>`` with the count in parentheses
        when known.
        """
        lines = [_render_entry(e) for e in self.entries]
        return "## gated sections\n\n" + "\n".join(lines)

    def resolve(self, handle: int) -> GatedSection | None:
        """The real `GatedSection` for a handle, or `None` if unknown.

        Closed-set: a handle the model returns that this digest never issued
        is dropped, never guessed into a fabricated section (ADR-0012/0020).
        """
        for entry in self.entries:
            if entry.handle == handle:
                return entry
        return None


def _render_entry(entry: GatedSection) -> str:
    if entry.stated_count is not None:
        return f"{{{{{entry.handle}}}}} {entry.label} ({entry.stated_count})"
    return f"{{{{{entry.handle}}}}} {entry.label}"


def _clean_text(node: Node) -> str:
    """`node`'s text content with noise tags excluded, matching the live-verified predicate.

    `Node.text(deep=True)` includes `<style>`/`<script>` contents — a real
    capture showed a "Reviews" panel reading as 2652 chars of non-empty text
    that was almost entirely an inlined `<style>` block; excluding noise tags
    left the genuine 573 chars of rendered review prose. The naive
    `node.text(deep=True)` would have misread that already-populated panel as
    a gate. `strip_tags` mutates `node`'s subtree in place — safe here since
    each panel is a disjoint subtree visited once per detection pass, and
    nothing downstream needs the panel's original markup back.
    """
    node.strip_tags(list(_NOISE_TAGS), recursive=True)
    return node.text(deep=True).strip()


def _is_in_nav(node: Node) -> bool:
    """True if `node` sits inside a `role="nav"` ancestor.

    The largest false-positive class (design.md D2/D3) is chrome-region
    counts — cart badges, notification badges — which live in nav regions.
    Prices, ratings and pagers are excluded structurally instead: they are
    never `role="tab"` or `<details>` controls in the first place.
    """
    current = node.parent
    while current is not None:
        if (current.attributes.get("role") or "").strip().lower() == "nav":
            return True
        current = current.parent
    return False


def _label_and_count(raw_label: str) -> tuple[str, int | None]:
    label = re.sub(r"\s+", " ", raw_label).strip()
    if not label:
        return label, None
    match = _TRAILING_COUNT_RE.match(label)
    if match:
        return match.group("label"), int(match.group("count"))
    return label, None


def _candidate_from_tab(tree: HTMLParser, node: Node) -> tuple[str, int | None] | None:
    """A `role="tab"` candidate, or `None` if its panel is populated / absent-of-signal.

    `aria-controls` names the panel by id; a tab with no `aria-controls`
    carries no resolvable panel and is skipped rather than guessed. `aria-label`
    is preferred over the element's own text — live capture showed the DOM text
    concatenates label and count with no separator (`"Soru Cevap4"`), while
    `aria-label` carries them space-separated (`" Soru Cevap 4"`), which is what
    makes the trailing-count split reliable.
    """
    panel_id = (node.attributes.get("aria-controls") or "").strip()
    if not panel_id:
        return None
    panel = tree.css_first(f'#{_css_escape(panel_id)}')
    if panel is not None and _clean_text(panel):
        return None  # populated panel — not a gate, just an inactive tab
    raw_label = (node.attributes.get("aria-label") or "").strip() or node.text(deep=True).strip()
    return _label_and_count(raw_label)


def _candidate_from_details(node: Node) -> tuple[str, int | None] | None:
    """A `<details>` without `open` whose body (besides `<summary>`) is empty."""
    if "open" in node.attributes:
        return None
    summary = node.css_first("summary")
    if summary is None:
        return None
    # `_clean_text(node)` strips noise tags recursively across the WHOLE
    # details subtree (including inside `summary`) before reading text — so
    # `summary`'s own text is read AFTER that same mutation, never separately
    # re-stripped, and the two reads are directly comparable.
    node_text = _clean_text(node)
    if not node_text:
        return None
    summary_text = summary.text(deep=True).strip()
    if not summary_text:
        return None
    if node_text != summary_text:
        return None  # details body carries more than the summary — not empty
    return _label_and_count(summary_text)


def _css_escape(value: str) -> str:
    """Minimal CSS.escape for an `id` selector — ids here are framework-generated
    tokens (`QuestionAnswers`), never attacker-controlled query input."""
    return re.sub(r"([^\w-])", r"\\\1", value)


def detect_gated_sections(html: str, *, limit: int = _DIGEST_GATE_CAP) -> GatedSectionDigest:
    """Scan `html` for disclosure controls whose panel was not retrieved.

    Pure, deterministic, recall-oriented (design.md D2) — precision is the
    extractor's job. Order is document order; handles are stable `{{1}}..{{n}}`
    in that order, capped by `limit`.
    """
    tree = HTMLParser(html)
    candidates: list[tuple[str, int | None]] = []
    seen_labels: set[str] = set()

    for tab in tree.css('[role="tab"]'):
        if _is_in_nav(tab):
            continue
        found = _candidate_from_tab(tree, tab)
        if found is None:
            continue
        label, count = found
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        candidates.append((label, count))

    for details in tree.css("details"):
        if _is_in_nav(details):
            continue
        found = _candidate_from_details(details)
        if found is None:
            continue
        label, count = found
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        candidates.append((label, count))

    candidates = candidates[:limit]
    entries = tuple(GatedSection(handle=i, label=label, stated_count=count) for i, (label, count) in enumerate(candidates, start=1))
    return GatedSectionDigest(entries=entries)
