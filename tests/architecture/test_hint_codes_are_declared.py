"""Every operator-hint code is drawn from one closed vocabulary.

`OperatorHint.code` is the field agents branch on, which makes it a wire
contract — and it was a bare `str`. A typo produced a hint that nothing could
match and nothing would report: the hint still rendered, still looked like a
signal, and every consumer's `if code == ...` quietly failed. For the ADR-0009
codes that is the difference between a loud miss and a silent one.

Two halves, because either alone leaves a hole:

- **Runtime** — `OperatorHint` validates `code` against `HINT_CODES`, so an
  undeclared code raises at construction rather than reaching the wire. That
  catches dynamically-built codes, which is what mattered: two real codes reach
  `OperatorHint` through a `code=reason` parameter and were invisible to any
  census of `code="..."` literals.
- **Static** (this file) — the source is walked for literal `code="..."` values,
  so a new one is caught at `make check` rather than when that branch first
  runs in production.
"""

from __future__ import annotations

import ast

from a2web.hints import HINT_CODES

from ._walk import SRC_ROOT, walked_files

_MIN_FILES = 20
#: Below the current population (23); a floor, not a count.
_MIN_CODES_FOUND = 12


def _literal_hint_codes() -> dict[str, str]:
    """Every literal `code="..."` keyword in `src/`, mapped to where it appears."""
    found: dict[str, str] = {}
    for path in walked_files(SRC_ROOT, minimum=_MIN_FILES):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - the gate's lint catches this first
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    found.setdefault(kw.value.value, f"{path.name}:{kw.lineno}")
    return found


def test_every_constructed_hint_code_is_declared() -> None:
    found = _literal_hint_codes()
    assert len(found) >= _MIN_CODES_FOUND, (
        f"found only {len(found)} literal hint code(s) — the walk or the AST match broke. Fix it rather than lowering the floor."
    )

    undeclared = sorted((code, where) for code, where in found.items() if code not in HINT_CODES)
    assert not undeclared, (
        "operator-hint code(s) constructed but absent from `models.HINT_CODES`:\n"
        + "".join(f"  {code}  ({where})\n" for code, where in undeclared)
        + "\n`code` is what agents branch on. An undeclared one matches nothing and "
        "reports nothing while still looking like a signal."
    )


def test_the_vocabulary_has_no_fossils() -> None:
    """The other direction, as a report rather than a failure.

    A declared code nobody constructs is usually rot — but not always: a code
    may legitimately be built dynamically (`code=reason`), which no literal
    census can see. So this asserts only that the vocabulary has not drifted
    into being MOSTLY fossils, which would mean the census is broken.
    """
    found = set(_literal_hint_codes())
    live = found & HINT_CODES
    assert len(live) >= _MIN_CODES_FOUND, (
        f"only {len(live)} of {len(HINT_CODES)} declared codes are constructed literally — the census is not working"
    )


def test_an_undeclared_code_is_rejected_at_construction() -> None:
    """Anti-vacuity for the runtime half: the validator must actually fire."""
    import pytest
    from pydantic import ValidationError

    from a2web.hints import OperatorHint

    with pytest.raises(ValidationError):
        OperatorHint(code="not_a_real_hint_code", message="x")

    # And a declared one still constructs.
    assert OperatorHint(code="llm_unavailable", message="x").code == "llm_unavailable"
