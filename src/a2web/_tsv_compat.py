"""TSV encoder — a byte-for-byte copy of a2kit's `packages/formatter/tsv.py`.

**Vendored deliberately, and deliberately not improved.** This is step 2 of the
a2kit sunset (`sunset-a2kit-dependency` Phase 2). Its whole job is to let a2web
stop importing a2kit's formatter while emitting *identical bytes*, so the wire
goldens under `tests/contracts/wire/` show zero deltas across the swap. Any
diff produced by this file is a regression, not a fix — do not tidy it, do not
"correct" the escaping, do not change the quoting policy here.

The escaping *is* wrong in a known way (stdlib `csv` with a tab delimiter
double-quotes cells containing `"`, `\\`, `\\t`, `\\n`, `\\r` rather than
escaping them), and the shelf's `lean-wire` package fixes it. That swap is a
separate change with a separate, bounded gate: every resulting delta must carry
the slug `lean-wire-escaping` and touch only such cells
(`tests/contracts/DELTAS.md`). Keeping the two moves apart is what makes it
possible to tell "we adopted the fix" from "we broke something".

This module is therefore temporary. It dies when `lean-wire` is adopted.

Upstream provenance: a2kit 0.49.2, `a2kit/packages/formatter/tsv.py`.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from pydantic import BaseModel


def _row_to_cells(row: Any, columns: list[str]) -> dict[str, Any]:
    if isinstance(row, BaseModel):
        dumped = row.model_dump(mode="json")
    elif isinstance(row, dict):
        dumped = row
    else:
        msg = f"encode_tsv expected BaseModel or dict rows, got {type(row).__name__}"
        raise TypeError(msg)

    return {
        col: (
            json.dumps(dumped[col], separators=(",", ":"), ensure_ascii=False)
            if isinstance(dumped.get(col), (list, dict))
            else (dumped[col] if dumped.get(col) is not None else "")
        )
        for col in columns
        if col in dumped
    }


def encode_tsv(rows: list[Any], *, columns: list[str]) -> str:
    """Encode `rows` as TSV with `columns` as the header.

    `rows` items may be pydantic `BaseModel` instances or plain dicts.
    `columns` SHOULD come from `Model.model_fields.keys()` (declared order) —
    alphabetical sorting would defeat the point.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(_row_to_cells(row, columns))
    return buf.getvalue()
