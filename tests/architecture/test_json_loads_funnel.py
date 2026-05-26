"""Architectural invariant: `json.loads` is funneled through `wobble/`.

Backstops Pattern 1 of ADR-0001 (the typed wobble funnel). The `Wobbled`
NewType prevents bypass at the *type* level for cooperative consumers; this
test prevents bypass at the *runtime* level — any new `json.loads` call
inside `src/a2web/packages/llm_extract/` outside `wobble/` fails CI.

Why this rule, not just a Tach interface check: Tach sees module-to-module
imports, not call sites. A consumer can `import json` legitimately for type
hints / json.dumps / json.JSONDecodeError without violating the funnel; the
violation is the `.loads(...)` call site specifically.

Acceptance check (re-run after any refactor):

    1. Open `src/a2web/packages/llm_extract/extractor.py`.
    2. Add `_ = json.loads("{}")` somewhere outside `wobble/`.
    3. Run `make arch`.
    4. Confirm this test fails with a precise file:line.
    5. Revert.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LLM_EXTRACT_ROOT = _REPO_ROOT / "src" / "a2web" / "packages" / "llm_extract"
_WOBBLE_DIR = _LLM_EXTRACT_ROOT / "wobble"


def _collect_json_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Find every binding that ends up referring to `json` module or `json.loads`.

    Returns `(module_aliases, loads_aliases)` — names that resolve to the json
    module (via `import json as X`) and names that resolve to `json.loads`
    directly (via `from json import loads as Y`).
    """
    module_aliases: set[str] = {"json"}
    loads_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "json":
                    module_aliases.add(alias.asname or "json")
        elif isinstance(node, ast.ImportFrom) and node.module == "json":
            for alias in node.names:
                if alias.name == "loads":
                    loads_aliases.add(alias.asname or "loads")
    return module_aliases, loads_aliases


def _is_json_loads(
    node: ast.Call, module_aliases: set[str], loads_aliases: set[str]
) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "loads":
        return isinstance(func.value, ast.Name) and func.value.id in module_aliases
    if isinstance(func, ast.Name):
        return func.id in loads_aliases
    return False


def test_no_json_loads_outside_wobble() -> None:
    violations: list[str] = []
    for path in _LLM_EXTRACT_ROOT.rglob("*.py"):
        # The funnel itself owns json.loads — skip wobble/.
        try:
            path.relative_to(_WOBBLE_DIR)
            continue
        except ValueError:
            pass

        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}:{exc.lineno}: syntax error parsing for funnel check")
            continue

        module_aliases, loads_aliases = _collect_json_aliases(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_json_loads(
                node, module_aliases, loads_aliases
            ):
                violations.append(
                    f"{path.relative_to(_REPO_ROOT)}:{node.lineno}: "
                    f"`json.loads(...)` outside `wobble/` — funnel through "
                    f"`parse_with_policy` or `parse_list_with_policy`"
                )

    assert not violations, (
        "Wobble funnel bypass detected. The funnel "
        "(`packages/llm_extract/wobble/parse_with_policy`) is the only legitimate "
        "json.loads site inside `packages/llm_extract/`:\n  "
        + "\n  ".join(violations)
    )
