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
"""

from __future__ import annotations

import ast
from pathlib import Path

from a2web.wire import _TSV_FIELDS

_MODELS = Path(__file__).resolve().parents[2] / "src" / "a2web" / "models.py"


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


def test_the_table_is_not_empty() -> None:
    """Anti-vacuity: an emptied table would pass both checks above."""
    assert set(_TSV_FIELDS) == {"query", "fetch_raw"}, f"the tool set changed: {sorted(_TSV_FIELDS)}"
    for tool, fields in _TSV_FIELDS.items():
        assert len(fields) >= 3, f"{tool} declares only {len(fields)} TSV field(s): {fields}"
