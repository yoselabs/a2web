"""The TSV field set is declared once, and both encoders agree with it.

Which fields render as a TSV table is a CONTRACT — `wire._TSV_FIELDS` states it
literally on purpose, because inferring it is how a field added to a response
model silently changes the agent-facing wire.

But there are two producers. `wire.encode_envelope` reads the table; the model
serializers (`FetchResponse._wire`, `AskResponse._wire`) hardcode their own
`encode_rows(...)` branches. Nothing made them agree, so a field could be TSV in
one and JSON in the other — and the disagreement would be invisible until an
agent parsed the wrong shape.

The split itself is deliberate and stays (§6.3): the model side chooses columns
from TYPED rows before `model_dump`, which is what lets a serializer elide a
field at its default without the column vanishing. Only the DECLARATION is
unified — the table is the single statement of which fields are tables.

**Which is why the two halves cannot literally consume one another** (§6.2, and
the reason that task resolved into this file rather than into an indirection).
Having a model-side branch is not redundant with being in the table — it decides
*which channel* carries TSV, and the two answers differ:

    field                model-side branch?   structured_content   content[0].text
    links                yes                  TSV string           TSV string
    next_links           yes                  TSV string           TSV string
    other_pages          yes                  TSV string           TSV string
    operator_hints       no                   JSON array           TSV string
    refinement_axes      no                   JSON array           TSV string
    options              no                   JSON array           TSV string
    content_candidates   no                   JSON array           TSV string

Both columns are intended. Machine consumers read `structured_content`; the
agent reads the text channel; a field pre-encoded model-side reaches both as
TSV because `encode_envelope`'s already-a-string guard passes it through. What
was NOT pinned before this file is the partition itself — adding or removing a
model-side `encode_rows` branch silently moves a field between those two rows,
changing what every machine consumer parses, with no test saying so. That is a
one-line edit away at all times, so it is asserted below.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from a2web.hints import OperatorHint
from a2web.models import AskResponse, FetchResponse, Link, ListingOption, NextLink, OtherPage, RefinementAxis
from a2web.wire import _TSV_FIELDS, encode_envelope, tsv_fields_for

_MODELS = Path(__file__).resolve().parents[2] / "src" / "a2web" / "models.py"

#: Fields whose TSV reaches BOTH channels because a model serializer pre-encodes
#: them. The complement of this set within `_TSV_FIELDS` is TSV on the text
#: channel only. Literal, for the same reason `_TSV_FIELDS` is: this is a wire
#: contract, and deriving it from the code under test would assert nothing.
_PRE_ENCODED_MODEL_SIDE = frozenset({"links", "next_links", "other_pages"})


def _model_side_tsv_fields() -> set[str]:
    """Fields the model serializers assign via `encode_rows(...)`.

    Matched as `tsv["<name>"] = encode_rows(...)`, which is the shape both
    serializers use.
    """
    tree = ast.parse(_MODELS.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        is_encode_rows = isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "encode_rows"
        if not is_encode_rows:
            continue
        if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
            found.add(target.slice.value)
    return found


def test_the_model_side_encodes_only_declared_fields() -> None:
    """A field the serializer tables must be declared in `_TSV_FIELDS`.

    The reverse direction is NOT asserted: the table legitimately names fields
    only `encode_envelope` handles (`operator_hints`, `refinement_axes`,
    `options`, `content_candidates`), which have no model-side branch. Only the
    model side is a subset.
    """
    model_side = _model_side_tsv_fields()
    assert len(model_side) >= 3, f"non-vacuous: expected the serializer TSV branches, found {sorted(model_side)}"

    declared = {field for fields in _TSV_FIELDS.values() for field in fields}
    undeclared = sorted(model_side - declared)

    assert not undeclared, (
        f"field(s) rendered as TSV by a model serializer but absent from `wire._TSV_FIELDS`: {undeclared}.\n"
        "The table is the single declaration of which fields are tables. A field "
        "tabled in one producer and not the other is a wire shape no consumer can predict."
    )


def test_no_declared_field_is_structurally_unencodable() -> None:
    """A declared field must be able to become a table at all.

    `headings` sat in both tuples and never rendered: `Heading` serializes to a
    compact `[level, text]` PAIR, so the dump is a list of LISTS and
    `encode_tsv` raises on a row that is neither a model nor a dict. The shape
    guard caught it every time and the field stayed a JSON array — a declaration
    the encoder structurally could not honour.

    This pins the specific case rather than attempting to prove encodability in
    general, which would require knowing every model's dump shape.
    """
    declared = {field for fields in _TSV_FIELDS.values() for field in fields}
    assert "headings" not in declared, (
        "`headings` is back in `_TSV_FIELDS`. It cannot render as TSV — "
        "`Heading` dumps as a `[level, text]` pair, so `encode_tsv` raises and "
        "the shape guard skips it. Declaring it claims a shape the encoder "
        "cannot produce."
    )


def _channels(response: AskResponse | FetchResponse, tool: str) -> dict[str, tuple[str, str]]:
    """Both wire channels for every declared TSV field of `tool`.

    Returns `{field: (structured_type, text_type)}` for the fields the response
    actually populates. Runs the real serializer and the real encoder — the
    partition is a property of those two, and asserting it against anything
    else would be asserting against a restatement of the thing under test.
    """
    structured = response.model_dump(mode="json")
    text = json.loads(encode_envelope(structured, tsv_fields_for(tool)))
    return {
        field: (type(structured[field]).__name__, type(text[field]).__name__)
        for field in tsv_fields_for(tool)
        if structured.get(field) is not None
    }


def test_the_model_side_branch_decides_which_channel_carries_tsv() -> None:
    """A field's TSV reaches `structured_content` only if a serializer pre-encodes it.

    Adding or deleting a `tsv[...] = encode_rows(...)` branch is a one-line edit
    that moves a field between "JSON array for machine consumers" and "TSV
    string for machine consumers". Nothing else in the suite notices: the
    ~1350 field-PRESENCE assertions read `call_wire` and the field is present
    either way, just a different type.
    """
    ask = AskResponse(
        url="https://example.org/a",
        status="ok",
        tier="raw",
        confidence="high",
        answer="x",
        other_pages=[OtherPage(url="https://example.org/b", reason="r", kind="drilldown")],
        operator_hints=[OperatorHint(code="cookies_stale", message="m", fix="f")],
        refinement_axes=[RefinementAxis(dimension="price floor", how="re-query with a minimum")],
        options=[ListingOption(title="an option")],
    )
    fetch = FetchResponse(
        url="https://example.org/a",
        status="ok",
        tier="raw",
        confidence="high",
        links=[Link(anchor="b", href="https://example.org/b")],
        next_links=[NextLink(url="https://example.org/c", reason="r", kind="drilldown", anchor="c")],
        operator_hints=[OperatorHint(code="cookies_stale", message="m", fix="f")],
    )

    observed = _channels(ask, "query") | _channels(fetch, "fetch_raw")
    assert len(observed) >= 6, f"non-vacuous: expected populated TSV fields on both envelopes, saw {sorted(observed)}"

    for field, (structured_type, text_type) in sorted(observed.items()):
        assert text_type == "str", f"{field} is declared TSV but reached the agent channel as {text_type}"
        expected = "str" if field in _PRE_ENCODED_MODEL_SIDE else "list"
        assert structured_type == expected, (
            f"`{field}` reached `structured_content` as {structured_type}, expected {expected}.\n"
            f"{'A model-side `encode_rows` branch was removed' if expected == 'str' else 'A model-side `encode_rows` branch was added'} "
            "— that changes what every machine consumer parses for this field. If the "
            "change is intended, move the field in `_PRE_ENCODED_MODEL_SIDE` and re-bless "
            "the wire goldens; do not silence this."
        )


def test_the_two_channel_partition_covers_the_whole_table() -> None:
    """Anti-vacuity: `_PRE_ENCODED_MODEL_SIDE` must name real declared fields."""
    declared = {field for fields in _TSV_FIELDS.values() for field in fields}
    stray = sorted(_PRE_ENCODED_MODEL_SIDE - declared)
    assert not stray, f"`_PRE_ENCODED_MODEL_SIDE` names field(s) absent from `_TSV_FIELDS`: {stray}"
    assert _PRE_ENCODED_MODEL_SIDE == _model_side_tsv_fields(), (
        "the pre-encoded set and the serializers' actual `encode_rows` branches disagree: "
        f"declared {sorted(_PRE_ENCODED_MODEL_SIDE)}, found {sorted(_model_side_tsv_fields())}"
    )


def test_the_table_is_not_empty() -> None:
    """Anti-vacuity: an emptied table would pass both checks above."""
    assert set(_TSV_FIELDS) == {"query", "fetch_raw"}, f"the tool set changed: {sorted(_TSV_FIELDS)}"
    for tool, fields in _TSV_FIELDS.items():
        assert len(fields) >= 3, f"{tool} declares only {len(fields)} TSV field(s): {fields}"
