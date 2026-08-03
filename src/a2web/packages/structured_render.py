"""Structured-data → markdown rendering. No a2web imports; no settings.

Lifted out of `a2web/domain.py` on 2026-08-01, where it was 381 of 551 lines
(69%) under a docstring reading *"pure functions reading `AppSettings` or domain
models but too small to deserve their own module"* — a description of the twelve
lines that were actually settings-coupled. The test tree already treated it as a
unit: four test files aimed at it directly, and it had zero a2web imports and was
`tach.toml`-eligible before the move. Only the source file disagreed.

**What this is.** A page's structured data (JSON-LD, microdata, OpenGraph, or a
framework's serialized state) rendered as markdown for the extraction LLM, plus
`listing_rows` — the same rows behind that markdown, returned as structure so
the wire index and the body cannot describe different item sets.

**What it is NOT.** It does not read `AppSettings`, know a `Verdict`, or decide
anything about a fetch. Everything it returns is derived from the payload it was
handed.

Three divergences were resolved during the move rather than carried across; each
is documented at its site: the second table renderer (`_rows_to_md_table`), the
`Recipe` allowlist (`_RECIPE_LABELS`), and the three unrelated bare `50`s
(`_LIST_SCAN_CAP`, `_RECORD_ROWS_CAP`, `_TABLE_ROWS_CAP`), one of which carried a
comment asking a human to keep two of them in sync by hand.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from json_in_html import ld_entries, microdata_to_ld

if TYPE_CHECKING:
    from json_in_html import JsonPayload

__all__ = (
    "json_response_fallback",
    "json_to_markdown_rows",
    "listing_rows",
)

_JSON_FALLBACK_CAP = 20_000


def json_response_fallback(data: dict | list) -> str:
    """Render an unrecognized JSON response body as a readable, capped code fence.

    The never-lose fallback for the JSON-response path: when
    `json_to_markdown_rows` doesn't recognize the shape, a valid-but-unknown
    payload still reaches the caller and the `ask` extractor as pretty-printed
    JSON, instead of a silent empty miss. Pure — no I/O.
    """
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if len(text) > _JSON_FALLBACK_CAP:
        text = text[:_JSON_FALLBACK_CAP] + "\n… (truncated)"
    return f"```json\n{text}\n```"


# --------------------------------------------------------------------- #
# JSON synthesis (v0.10 — harsh-test-session-fixes)
# --------------------------------------------------------------------- #


def json_to_markdown_rows(payload: JsonPayload) -> str:
    """Convert a `JsonPayload` to a synthetic markdown surface for the
    extractor LLM.

    Only known shapes are converted; unknown shapes return an empty string
    (the caller will then fall back to the original trafilatura output).
    Recognized shapes:

    * LD-JSON `Product` / `NewsArticle` / `Article` (single or `@graph`)
    * LD-JSON `ItemList` (`itemListElement`)
    * Next.js `props.pageProps.products` / `props.pageProps.items`
    * Generic `products` / `items` array at the root

    The output is a markdown table when the data is row-shaped, or a
    `**key:** value` list when it's a single entity. Empty input → empty
    output (do-no-harm contract).
    """
    if payload is None:
        return ""
    data = payload.data
    if payload.source == "ld_json":
        return _ld_json_to_markdown(data)
    if payload.source in ("next_data", "nuxt_data", "window_var", "generic"):
        return _framework_state_to_markdown(data)
    if payload.source == "microdata":
        return _ld_json_to_markdown(microdata_to_ld(data))
    if payload.source == "opengraph":
        return _opengraph_to_markdown(data)
    return ""


#: Types with their OWN renderer below. Not an allowlist — everything else
#: falls through to the type-agnostic default-keep path, which is the point.
_SPECIAL_TYPES = frozenset({"ItemList", "BreadcrumbList"})

#: How many JSON-LD entities one payload renders. A bound, not a filter: a page
#: publishing forty `ImageObject`s must not crowd out its `Product`, but the cut
#: is by VOLUME (declared below) rather than by a vocabulary a2web holds.
#: `declared_cap_v5` measured the shape of this trade on the sibling wire path —
#: coverage saturates around 20 fields and the tail is inert.
_ENTITY_COUNT_CAP = 12


def _ld_json_to_markdown(data: dict | list) -> str:
    entries = ld_entries(data)
    if not entries:
        return ""
    lines: list[str] = []
    rendered = 0
    dropped = 0
    for entry in entries:
        t = entry.get("@type")
        if isinstance(t, list):
            t = t[0] if t else None
        if t not in _SPECIAL_TYPES:
            # DEFAULT-KEEP, no type gate (ADR-0018). This was an eight-name
            # allowlist — `Product`, `Article`, `NewsArticle`, `LocalBusiness`,
            # `Organization`, `ContactPoint`, `Event`, `Recipe` — and every
            # other declared type rendered as NOTHING. Measured on 2026-08-03
            # (`declaration_rate_v6`): a closed list drops 4 of the 7 corpus
            # pages that declare anything subject-level, including a 74-field
            # `ProductGroup`, a 51-field `DiscussionForumPosting` and a
            # 35-field `NewsMediaOrganization`. The renderer never needed the
            # list — `_single_entity_md` takes the type as a plain string
            # LABEL and reads the entity's own keys, so passing an unknown type
            # through costs nothing and recovers everything.
            #
            # An unnamed entity carrying no renderable field yields "" and is
            # dropped by the final join, so chrome does not become noise.
            if rendered >= _ENTITY_COUNT_CAP:
                dropped += 1
                continue
            md = _single_entity_md(entry, kind=str(t) if t else "Thing")
            if md:
                lines.append(md)
                rendered += 1
        elif t == "ItemList":
            rows = _item_list_rows(entry)
            if rows:
                lines.append(_render_rows(rows, title="ItemList"))
        elif t == "BreadcrumbList":
            items = entry.get("itemListElement") or []
            names = [it.get("name") for it in items if isinstance(it, dict) and it.get("name")]
            if names:
                lines.append("**Breadcrumbs:** " + " > ".join(names))
    if dropped:
        # DECLARE the cut. A reader who cannot tell "the page published this
        # much" from "a2web stopped rendering" will read the first into the
        # second (ADR-0009). `dropped` differs from `rendered` by construction,
        # so unlike `hn`'s old note this one can actually fire.
        lines.append(f"_… {dropped} further structured entit{'y' if dropped == 1 else 'ies'} not shown._")
    return "\n\n".join(s for s in lines if s)


def _item_list_rows(entry: dict) -> list[dict]:
    """The normalized rows of one JSON-LD `ItemList` entry.

    Split out of `_ld_json_to_markdown` so the SAME rows can back both the
    synthetic markdown and the wire index — see `listing_rows`.
    """
    items = entry.get("itemListElement") or []
    raw_rows = [item.get("item", item) if isinstance(item, dict) else None for item in items]
    return [_normalize_commerce_row(r) for r in raw_rows if isinstance(r, dict)]


def _framework_state_rows(data: dict | list) -> list[dict]:
    """The normalized rows behind a framework-state (Next/Nuxt/window-var) render."""
    rows = _find_product_or_item_list(data)
    return [_normalize_commerce_row(r) for r in rows] if rows else []


def _framework_state_to_markdown(data: dict | list) -> str:
    rows = _framework_state_rows(data)
    if rows:
        return _render_rows(rows, title="Listings")
    return ""


def listing_rows(payload: JsonPayload) -> list[dict]:
    """The listing rows behind a payload's synthetic markdown, or `[]`.

    **Why this exists (ADR-0015).** `json_to_markdown_rows` renders an embedded
    `ItemList` into rich markdown — name, url, price, rating per item — and then
    throws the structure away, returning a string. The DOM record-miner path
    keeps its `RecordSet`, so it feeds `other_pages` and the `options` shelf; the
    JSON-LD path fed neither. A catalog page whose items live in JSON-LD (the
    common shape for commerce and for most SSR'd listings) therefore returned an
    answer with NO index of what it withheld — every product URL sat in the
    rendered markdown and reached the caller nowhere. That is the ADR-0015 harm
    exactly: withholding the body without leaving the index.

    Returns the same rows the markdown was rendered from, so the two cannot
    describe different item sets. Non-listing payloads (a single `Product`, an
    `Article`, OpenGraph) return `[]` — an entity is not an index.
    """
    if payload is None:
        return []
    data = payload.data
    if payload.source == "microdata":
        data = microdata_to_ld(data)
    elif payload.source in ("next_data", "nuxt_data", "window_var", "generic"):
        return _framework_state_rows(data)
    elif payload.source != "ld_json":
        return []

    rows: list[dict] = []
    for entry in ld_entries(data):
        entry_type = entry.get("@type")
        if isinstance(entry_type, list):
            entry_type = entry_type[0] if entry_type else None
        if entry_type == "ItemList":
            rows.extend(_item_list_rows(entry))
    return rows


def _find_product_or_item_list(data: Any, depth: int = 0) -> list[dict]:
    """Walk the JSON looking for a list of objects under a key like
    `products`, `items`, `results`, `entities`. Capped at depth 6 so we
    don't explore the entire app state."""
    if depth > 6:
        return []
    if isinstance(data, dict):
        for key in ("products", "items", "results", "entities", "list"):
            v = data.get(key)
            if isinstance(v, list) and v and all(isinstance(item, dict) for item in v):
                return v[:_LIST_SCAN_CAP]
        for v in data.values():
            found = _find_product_or_item_list(v, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_product_or_item_list(item, depth + 1)
            if found:
                return found
    return []


# --- The three caps that were all spelled `50` ------------------------------
#
# They were three unrelated bounds sharing a literal, and one carried a comment
# ("cap synthetic output, matching _find_product_or_item_list") asking a human to
# keep two of them in sync BY HAND. A manual sync is a poor invariant inside one
# file and an unenforceable one across a package boundary, so the move names each
# for what it bounds and lets them move independently.

#: How many rows to take from a framework-state array (`products`, `items`, …).
#: Bounds the SCAN — a page's app state can hold thousands of rows and walking
#: all of them costs time before anything is rendered.
_LIST_SCAN_CAP = 50

#: How many linked records `_rows_to_md_records` renders. Bounds the OUTPUT, so
#: an oversized listing cannot dominate the extraction prompt.
_RECORD_ROWS_CAP = 50

#: How many rows `_rows_to_md_table` renders. Same job as `_RECORD_ROWS_CAP` for
#: the other renderer; it had NO row cap at all before the move, so a 900-row
#: table went to the LLM whole.
_TABLE_ROWS_CAP = 50

#: Per-cell character cap in the rendered table. Unified at 200 (the OpenGraph
#: renderer's value) rather than 80 (the table's): the cells that get truncated
#: are descriptions and titles, and cutting one at 80 characters drops
#: answer-bearing prose the caller cannot recover without another fetch.
_TABLE_CELL_CAP = 200

#: Column cap, and the columns are the UNION over EVERY row rather than a sample.
#: The pre-move version inferred them from the first five rows, so a key absent
#: from all five was deleted from the table for every row that had it — the same
#: defect `wire.encode_rows` was fixed for on 2026-07-31, one renderer over.
#: Rows are heterogeneous by construction; a sample cannot describe them.
_TABLE_COLUMN_CAP = 8


# Known chrome dropped by the default-keep entity renderer — JSON-LD machinery
# is handled by the `@`-prefix check; these are media/self-reference keys whose
# values are never answer-bearing prose.
_ENTITY_NOISE_KEYS = frozenset({"image", "thumbnail", "thumbnailurl", "logo", "mainentityofpage"})
# Cap a single field's rendered value so a full `articleBody` (or similar) isn't
# dumped into a key-value line; the prose candidate already carries long text.
_ENTITY_VALUE_CAP = 500
# Defensive cap on rendered array-of-dict entries (e.g. multiple `ContactPoint`s)
# so a pathological page's oversized array can't bloat the extraction prompt.
_ENTITY_ARRAY_CAP = 10


def _scalar_kv(k: object, v: object) -> bool:
    """A renderable answer-bearing key/value: a non-`@` string key with a
    non-empty scalar value."""
    return isinstance(k, str) and not k.startswith("@") and isinstance(v, (str, int, float)) and str(v) != ""


#: Friendly labels for the `Recipe` fields that have them. NOT an allowlist —
#: every other field still renders by default-keep. Before the move this table
#: WAS the allowlist, and everything absent from it was dropped: a recipe page's
#: `recipeInstructions` — the steps, the single most answer-bearing field on the
#: page — reached the caller nowhere, alongside `recipeCuisine`,
#: `recipeCategory`, `aggregateRating`, `keywords` and `suitableForDiet`.
#:
#: `_single_entity_md`'s own docstring argues that an allowlist "silently loses
#: an unanticipated answer-bearing field" (ADR-0004 default-keep). It was right,
#: and `_recipe_md` was the counterexample sitting thirty lines above it.
_RECIPE_LABELS: dict[str, str] = {
    "recipeYield": "Yield",
    "prepTime": "Prep",
    "cookTime": "Cook",
    "totalTime": "Total",
    "recipeIngredient": "Ingredients",
    "recipeInstructions": "Instructions",
    "nutrition": "Nutrition",
}


def _single_entity_md(entry: dict, *, kind: str) -> str:
    """Render a single JSON-LD entity by **default-keep** (ADR-0004): surface
    every answer-bearing scalar / shallow field in the entity's own order,
    dropping only JSON-LD machinery (`@`-keys), media/self-reference keys, and
    oversized values. No fixed `interesting_keys` allowlist — an unanticipated
    answer-bearing field (a `gtin`, a `material`) is no longer silently lost.
    A list-of-dicts field (e.g. `Organization.contactPoint` holding multiple
    `ContactPoint` entries) renders each entry as its own sub-line rather than
    silently vanishing, capped at `_ENTITY_ARRAY_CAP` entries."""
    name = entry.get("name") or entry.get("headline") or "unnamed"
    lines = [f"## {kind}: {name}"]
    for key, val in entry.items():
        if not isinstance(key, str) or key.startswith("@") or key.lower() in _ENTITY_NOISE_KEYS:
            continue
        if isinstance(val, dict):
            inner = ", ".join(f"{k}={v}" for k, v in val.items() if _scalar_kv(k, v))
            if inner:
                lines.append(f"- **{_label(key)}:** {inner}")
        elif isinstance(val, list):
            dict_entries = [v for v in val if isinstance(v, dict)]
            if dict_entries:
                lines.append(f"- **{_label(key)}:**")
                for sub in dict_entries[:_ENTITY_ARRAY_CAP]:
                    sub_inner = ", ".join(f"{k}={v}" for k, v in sub.items() if _scalar_kv(k, v))
                    if sub_inner:
                        lines.append(f"  - {sub_inner}")
            else:
                scalars = [str(v) for v in val if isinstance(v, (str, int, float)) and str(v)]
                joined = ", ".join(scalars)
                if joined:
                    lines.append(f"- **{_label(key)}:** {_capped(joined)}")
        elif isinstance(val, (str, int, float)):
            text = str(val)
            if text:
                lines.append(f"- **{_label(key)}:** {_capped(text)}")
    # A header with nothing under it is noise, not content. This mattered
    # little while an eight-name allowlist stood in front (a `Product` almost
    # always has fields); once the gate came off (ADR-0018), every page's
    # `ImageObject` / `SiteNavigationElement` chrome reached here and would
    # have rendered a wall of `## ImageObject: unnamed` stubs. Emptiness is
    # decided by CONTENT — which is what makes the type gate unnecessary rather
    # than merely wrong.
    if len(lines) == 1 and name == "unnamed":
        return ""
    return "\n".join(lines)


def _label(key: str) -> str:
    """A friendly label where one exists, else the schema key verbatim."""
    return _RECIPE_LABELS.get(key, key)


def _capped(text: str) -> str:
    """Cap an over-long value VISIBLY.

    It used to be dropped: `if len(s) <= _ENTITY_VALUE_CAP` with no else, so a
    field over the cap vanished entirely. On a real recipe that is the whole
    ingredient list — thirty items joined comfortably exceed 500 characters —
    and on a product it is any long spec string. Silent loss where truncation
    was intended; the caller could not tell the field was absent from the page
    versus dropped on the way out (ADR-0009).
    """
    if len(text) <= _ENTITY_VALUE_CAP:
        return text
    return text[: _ENTITY_VALUE_CAP - 1].rstrip() + "…"


def _normalize_commerce_row(row: dict) -> dict:
    """Promote nested schema.org commerce fields to top-level scalars so the
    synth renderer can surface them: `offers.price` + `offers.priceCurrency`
    → a combined `price` token (e.g. `3690 TRY`), `offers.url` → `url`, and
    `aggregateRating.ratingValue` → `rating`. Flat-shaped rows (top-level
    scalar `price`/`url`) and non-commerce rows pass through unchanged."""
    if not isinstance(row, dict):
        return row
    out = dict(row)
    offers = row.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        if price is not None and out.get("price") is None:
            currency = offers.get("priceCurrency")
            out["price"] = f"{price} {currency}" if currency else str(price)
        url = offers.get("url")
        if url and not out.get("url"):
            out["url"] = url
    rating = row.get("aggregateRating")
    if isinstance(rating, dict):
        rv = rating.get("ratingValue")
        if rv is not None and out.get("rating") is None:
            out["rating"] = rv
    return out


def _is_commerce_shaped(rows: list[dict]) -> bool:
    """A list is commerce-shaped when at least half its rows carry a (lifted)
    `price` or `url` — the gate that routes to linked-record rendering."""
    if not rows:
        return False
    hits = sum(1 for r in rows if isinstance(r, dict) and (r.get("price") is not None or r.get("url")))
    return hits * 2 >= len(rows)


def _render_rows(rows: list[dict], *, title: str) -> str:
    """Render row-shaped data: linked records for commerce-shaped lists
    (price/url preserved verbatim), the fixed-width table otherwise."""
    if _is_commerce_shaped(rows):
        return _rows_to_md_records(rows, title=title)
    return _rows_to_md_table(rows, title=title)


def _sanitize_link_text(text: str) -> str:
    """Make a string safe as markdown link text: drop `[`/`]` (which would
    terminate the link) and collapse any whitespace/newlines to single
    spaces."""
    return " ".join(str(text).replace("[", "").replace("]", "").split())


def _rows_to_md_records(rows: list[dict], *, title: str) -> str:
    """Render commerce rows as linked markdown records — one per item:
    `- [name](url) — 3690 TRY ⭐ 4.7`. The url is never length-capped (unlike
    the table's per-cell cap), so it stays verbatim for other_pages drilldowns.
    Absent fields are omitted; `image` is intentionally not rendered."""
    lines: list[str] = []
    for row in rows[:_RECORD_ROWS_CAP]:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("headline") or row.get("title")
        url = row.get("url")
        if not name and not url:
            continue
        if url and name:
            head = f"[{_sanitize_link_text(name)}]({url})"
        elif name:
            head = _sanitize_link_text(name)
        else:
            head = str(url)
        extras: list[str] = []
        price = row.get("price")
        if price is not None and str(price) != "":
            extras.append(str(price))
        rating = row.get("rating")
        if rating is not None and str(rating) != "":
            extras.append(f"⭐ {rating}")
        line = f"- {head}"
        if extras:
            line += " — " + " ".join(extras)
        lines.append(line)
    if not lines:
        return ""
    return f"### {title}\n\n" + "\n".join(lines)


def _rows_to_md_table(rows: list[dict], *, title: str) -> str:
    """Render rows as a markdown table. THE table renderer — there were two.

    `_opengraph_to_markdown` hand-rolled a second one twelve lines below this,
    with the same escaping and the same header shape but a different cell cap
    (200 vs 80) and a different row cap (50 vs none). Two renderers meant every
    fix landed in one of them; the move keeps one and OpenGraph now feeds it.

    Columns are the UNION over every row, not a sample of the first five. Rows
    are heterogeneous by construction here — `_normalize_commerce_row` promotes
    `price`/`url`/`rating` only where the source carries them — so a key absent
    from the first five rows was deleted from the table for every row that had
    it. That is the defect `wire.encode_rows` was fixed for on 2026-07-31, in
    the other renderer, and it is why a sample can never define the columns.
    """
    columns: list[str] = []
    for row in rows:
        for k, v in row.items():
            if k.startswith("@") or isinstance(v, (dict, list)):
                continue
            if k not in columns:
                columns.append(k)
    columns = columns[:_TABLE_COLUMN_CAP]
    if not columns:
        return ""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    shown = rows[:_TABLE_ROWS_CAP]
    body_lines = []
    for row in shown:
        cells = []
        for k in columns:
            v = row.get(k, "")
            if isinstance(v, (dict, list)):
                v = ""
            cells.append(str(v).replace("|", "/")[:_TABLE_CELL_CAP])
        body_lines.append("| " + " | ".join(cells) + " |")
    out = f"### {title}\n\n" + "\n".join([header, sep, *body_lines])
    if len(rows) > len(shown):
        # Declared, not silent — the same rule the handlers were brought to on
        # 2026-08-01. A table cut to 50 of 900 with no note reads as complete.
        out += f"\n\n_Showing {len(shown)} of {len(rows)} rows — this is a partial view._"
    return out


# --------------------------------------------------------------------- #
# extruct adapters (v0.18)
# --------------------------------------------------------------------- #


def _opengraph_to_markdown(data: dict | list) -> str:
    """Render the OpenGraph dict as a two-column table via THE table renderer.

    This used to hand-roll its own table twelve lines below the one it could
    have called — same escaping, same header shape, different caps. Keeping both
    guaranteed that any fix to one missed the other, which is exactly what
    happened: the column-sampling bug lived in `_rows_to_md_table` and this copy
    was immune, so neither renderer was ever wholly right.

    The extractor emits a flat `{property: content}` dict for OG; list input is
    handled defensively in case a future producer chooses that shape.
    """
    flat: dict[str, str] = {}
    if isinstance(data, dict):
        flat = {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                for k, v in entry.items():
                    if isinstance(v, (str, int, float)):
                        flat[str(k)] = str(v)
    if not flat:
        return ""
    rows = [{"property": k, "value": v} for k, v in flat.items()]
    return _rows_to_md_table(rows, title="OpenGraph")
