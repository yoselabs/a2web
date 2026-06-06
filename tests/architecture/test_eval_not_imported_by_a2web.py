"""Architectural invariant: the shipped `a2web` package never imports the
eval harness.

Evals are tests, and the product must not depend on its own test/dev
tooling. The replay-cassette format, the capture/refresh scripts, and the
on-disk corpus loader all live under the non-packaged top-level `eval/`
package. Any `import eval` / `from eval...` inside `src/a2web/` would ship
the harness into the wheel and invert the dependency — so it fails CI.

Acceptance check (re-run after any refactor):

    1. Add `from eval._capture.cassette import parse_exchanges` to any
       module under `src/a2web/`.
    2. Run `make arch`.
    3. Confirm this test fails with a precise file:line.
    4. Revert.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_A2WEB_SRC = _REPO_ROOT / "src" / "a2web"


def _imports_eval(tree: ast.AST) -> list[int]:
    """Return line numbers of any `import eval` / `from eval[...] import`."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "eval" or alias.name.startswith("eval."):
                    hits.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for `from . import x`; relative imports
            # within a2web can never reach the top-level `eval` package.
            if node.level == 0 and node.module and (node.module == "eval" or node.module.startswith("eval.")):
                hits.append(node.lineno)
    return hits


def test_a2web_does_not_import_eval_harness() -> None:
    offenders: list[str] = []
    for path in _A2WEB_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for lineno in _imports_eval(tree):
            offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}")
    assert not offenders, (
        "a2web product code must not import the `eval/` test harness "
        "(evals are tests — the product cannot depend on them):\n  " + "\n  ".join(offenders)
    )
