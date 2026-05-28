"""Architectural invariant: no `dict[str, Any]` fields on slotted dataclasses.

`dict[str, Any]` bags are the "typed pipeline object → untyped dict bag"
escape hatch. CLAUDE.md "Never reintroduce `tier_extras: dict[str, Any]`" is
the rule; this test makes it structural.

Allowlist below is the *known-acceptable* set — surfaces where the data
genuinely is heterogeneous (raw provider payloads, etc.). Adding to the
allowlist requires a comment explaining why a typed field can't replace it.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"

# Known-acceptable `dict[str, Any]` fields. Each entry: module-relative file
# path + field name + reason.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        # ExtractionResult.raw carries provider-side prompt/completion-token
        # metrics whose shape varies by provider (anthropic vs claude-code).
        ("packages/llm_extract/extractor.py", "raw"),
        # JudgeVerdict.raw carries the same provider-side metrics + an
        # optional `reached_derived` flag set by the funnel.
        ("packages/llm_extract/judge.py", "raw"),
        # ProviderResponse.raw is the literal provider HTTP response body —
        # heterogeneous by construction.
        ("packages/llm_extract/providers/base.py", "raw"),
        # AppSettings receives env/YAML values whose shape is user-controlled
        # at the boundary — pydantic-settings owns coercion downstream.
        ("settings.py", "raw_extras"),
        # Eval-harness metadata bags. These are bench-only and carry
        # heterogeneous run shape (system-specific fields, optional debug
        # captures); the harness owns coercion at the report-rendering seam.
        # If a third consumer materializes, lift to typed sub-objects.
        ("llm_eval/runner.py", "fetch_metadata"),
        ("llm_eval/systems.py", "metadata"),
        ("llm_eval/extraction.py", "extra"),
        ("llm_eval/corpus.py", "extra"),
    }
)


def _is_dict_str_any(annotation: ast.AST) -> bool:
    """Match `dict[str, Any]` / `Dict[str, Any]` / `dict[str, Any] | None`."""
    if isinstance(annotation, ast.Subscript):
        value = annotation.value
        if isinstance(value, ast.Name) and value.id in ("dict", "Dict"):
            # Extract slice — could be Tuple of (key_type, value_type).
            slc = annotation.slice
            if isinstance(slc, ast.Tuple) and len(slc.elts) == 2:
                key, val = slc.elts
                return isinstance(key, ast.Name) and key.id == "str" and isinstance(val, ast.Name) and val.id == "Any"
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _is_dict_str_any(annotation.left) or _is_dict_str_any(annotation.right)
    return False


def _is_slotted_dataclass(decorators: list[ast.expr]) -> bool:
    for dec in decorators:
        # @dataclass(slots=True) / @dataclass(frozen=True, slots=True) / @dataclass()
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id == "dataclass":
                # Accept bare @dataclass() too — slots=True is the strict subset.
                # The intent is "internal pipeline objects"; @dataclass() qualifies.
                return True
            if isinstance(func, ast.Attribute) and func.attr == "dataclass":
                return True
        elif isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        elif isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            return True
    return False


def test_no_dict_str_any_on_dataclasses() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_slotted_dataclass(node.decorator_list):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    field_name = stmt.target.id
                    if (rel, field_name) in _ALLOWLIST:
                        continue
                    if _is_dict_str_any(stmt.annotation):
                        violations.append(
                            f"{rel}:{stmt.lineno}: `{node.name}.{field_name}: "
                            f"dict[str, Any]` — declare a typed field instead, "
                            f"or add to the allowlist with rationale"
                        )

    assert not violations, "Untyped `dict[str, Any]` field on dataclass detected. Typed pipeline objects beat dict bags:\n  " + "\n  ".join(
        violations
    )
