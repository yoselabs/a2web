"""TSV tables must not drop a field that only some rows carry.

`_derive_columns` used to read the FIRST row's keys, while
`OperatorHint._omit_default_severity` drops `severity` when it is the default
`info`. Together: an `info` hint followed by a `critical` one produced a table
with no `severity` column, and the `critical` value was discarded on the way
to the agent.

`try_user_browser` is ADR-0009's loudest signal — *a wall stopped us, go look
yourself* — so the field that marks it critical is exactly the one that must
survive. `structured_content` was never affected, which is why ~1350
field-presence assertions missed this: they all read `call_wire`. **The agent
reads `content[0].text`.** Every assertion here reads that channel.
"""

from __future__ import annotations

import json

from a2web.hints import OperatorHint
from a2web.models import AskResponse, OtherPage
from a2web.wire import encode_envelope, tsv_fields_for


def _encode_query(payload: dict) -> dict:
    """Encode `payload` exactly as `EnvelopeContentMiddleware` would."""
    return json.loads(encode_envelope(payload, tsv_fields_for("query")))


def _rows(block: str) -> tuple[list[str], list[list[str]]]:
    """Split a TSV block into its header and body cells."""
    lines = block.rstrip("\n").split("\n")
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def test_critical_severity_survives_a_preceding_info_hint() -> None:
    """An `info` hint first must not erase the `critical` marker of a later one."""
    hints = [
        OperatorHint(code="cookies_stale", message="mirror is stale", fix="refresh"),
        OperatorHint(
            code="try_user_browser",
            message="This URL was NOT retrieved",
            fix="open it in a real browser tool",
            severity="critical",
        ),
    ]
    payload = {"answer": "a", "operator_hints": [h.model_dump(mode="json") for h in hints]}

    header, body = _rows(_encode_query(payload)["operator_hints"])

    assert "severity" in header, f"severity column dropped, header was {header}"
    severity = body[1][header.index("severity")]
    assert severity == "critical", f"the ADR-0009 klaxon reached the agent stripped of its severity: got {severity!r} from row {body[1]!r}"


def test_a_row_missing_a_union_column_renders_an_empty_cell() -> None:
    """Widening the header must not shift the sparse row's values sideways."""
    hints = [
        OperatorHint(code="cookies_stale", message="m1", fix="f1"),
        OperatorHint(code="try_user_browser", message="m2", fix="f2", severity="critical"),
    ]
    payload = {"answer": "a", "operator_hints": [h.model_dump(mode="json") for h in hints]}

    header, body = _rows(_encode_query(payload)["operator_hints"])

    assert all(len(row) == len(header) for row in body), "every row is header-width"
    info_row = dict(zip(header, body[0], strict=True))
    assert info_row["severity"] == "", "an elided field is an empty cell, not a shifted one"
    assert info_row["code"] == "cookies_stale", "scalar columns keep their values"
    assert info_row["message"] == "m1"


def test_sparse_first_row_does_not_hide_a_later_column() -> None:
    """The union rule is order-independent: leading sparse rows still widen."""
    pages = [
        OtherPage(url="https://example.org/a", reason="same site", kind="drilldown"),
        OtherPage(
            url="https://elsewhere.test/b",
            reason="off-site",
            kind="drilldown",
            off_domain=True,
        ),
    ]
    response = AskResponse(
        url="https://example.org/docs",
        status="ok",
        tier="raw",
        confidence="high",
        answer="two pointers",
        other_pages=pages,
    )

    header, body = _rows(response.model_dump(mode="json")["other_pages"])

    assert "off_domain" in header, f"ADR-0014's off-domain flag must ride the wire when ANY row sets it, header was {header}"
    assert body[1][header.index("off_domain")] == "True"
