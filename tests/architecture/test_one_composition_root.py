"""There is exactly ONE place a2web builds its object graph.

`components.build_components()` absorbed `bootstrap_state`. The risk it
absorbed with it: before the sunset, a2web had *two* construction paths — the
a2kit provider chain in `server.py` and `bootstrap_state` for the eval CLI and
tests — and a resource added to one could miss the other. That gap was real and
cost a bench-harness bug in v0.22.

Hand-wiring makes a second root cheap to write by accident: any module can call
the `state.py` factories directly and assemble its own graph, and the result
will *work* while quietly diverging from production. So the rule is structural
rather than cultural, mirroring a2kay.

The factories in `state.py` stay the single source of truth for *how* each
resource is constructed; `components.py` is the single source of truth for
*when*, and this test pins that only one module holds the second answer.
"""

from __future__ import annotations

import ast

from ._walk import REPO_ROOT, SRC_ROOT, walked_files

#: The per-resource factories. Calling one is how you construct a resource;
#: calling several in one module is how you build a second composition root.
_FACTORIES = frozenset(
    {
        "build_breakers",
        "build_proxy_pool",
        "build_browser_backend",
        "build_browser_robust_backend",
        "build_selected_provider",
        "build_llm_extractor",
        "build_cookie_jar",
        "build_state",
    }
)

#: The one composition root, plus the module that defines the factories.
_ALLOWED = frozenset({"components.py", "state.py"})

#: More than this many distinct factories in one module IS a composition root.
_ROOT_THRESHOLD = 3


def test_only_components_assembles_the_graph() -> None:
    offenders: list[str] = []
    for path in walked_files(SRC_ROOT, minimum=80):
        if path.name in _ALLOWED:
            continue
        tree = ast.parse(path.read_text())
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FACTORIES
        }
        if len(called) > _ROOT_THRESHOLD:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: calls {sorted(called)}")

    assert not offenders, (
        "a second composition root appeared:\n  "
        + "\n  ".join(offenders)
        + "\n\nBuild the graph through `a2web.components.build_components(...)`, "
        "passing a `*_factory` override for anything that needs to differ. A "
        "parallel root works right up until a resource is added to one root and "
        "not the other."
    )
