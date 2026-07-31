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

from ._walk import walked_files

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


def _is_json_loads(node: ast.Call, module_aliases: set[str], loads_aliases: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "loads":
        return isinstance(func.value, ast.Name) and func.value.id in module_aliases
    if isinstance(func, ast.Name):
        return func.id in loads_aliases
    return False


#: `llm_eval/` parses LLM output too (`bench_judge.py` runs the clarity and
#: next_links judges), and the guard walked only `packages/llm_extract/`, so it
#: was never inspected. It was already funnelling through `parse_with_policy`;
#: adding the root locks that in at the cheap moment rather than after a
#: regression.
#:
#: **The whole `src/a2web` tree is deliberately NOT walked.** Five sites there
#: call `json.loads` on UPSTREAM API responses — HN's Algolia payload, discourse,
#: v2ex, habr, the archive CDX rows. Those are not LLM output and the wobble
#: funnel is not for them: it exists because a model emits *almost* the agreed
#: contract, which is a different failure than an API returning malformed JSON
#: (that is simply a broken response, and the tier's verdict machinery owns it).
#: Widening this guard to the whole tree would flag five correct call sites and
#: pressure someone into routing API parsing through a policy table built for
#: model wobble.
#:
#: The remaining named site, `fetcher_response.py::_project_routing`, does not
#: call `json.loads` at all — it pydantic-validates an already-parsed payload —
#: so there is nothing here for this guard to check.
_JUDGE_ROOTS = (_REPO_ROOT / "src" / "a2web" / "llm_eval",)


def test_no_json_loads_outside_wobble() -> None:
    violations: list[str] = []
    walked = list(walked_files(_LLM_EXTRACT_ROOT, minimum=6))
    for root in _JUDGE_ROOTS:
        walked.extend(walked_files(root, minimum=3))
    for path in walked:
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
            if isinstance(node, ast.Call) and _is_json_loads(node, module_aliases, loads_aliases):
                violations.append(
                    f"{path.relative_to(_REPO_ROOT)}:{node.lineno}: "
                    f"`json.loads(...)` outside `wobble/` — funnel through "
                    f"`parse_with_policy` or `parse_list_with_policy`"
                )

    assert not violations, (
        "Wobble funnel bypass detected. The funnel "
        "(`packages/llm_extract/wobble/parse_with_policy`) is the only legitimate "
        "json.loads site inside `packages/llm_extract/`:\n  " + "\n  ".join(violations)
    )
