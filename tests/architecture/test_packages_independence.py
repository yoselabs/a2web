"""Architectural invariant: `a2web.packages.*` is domain-independent.

Modules under `src/a2web/packages/` MUST NOT import from a2web's domain
modules. They may import from:
- stdlib
- third-party libraries (pinned in pyproject.toml)
- `a2web.packages.*` (sibling packages)
- `a2web.utils.*` (genuinely-shared primitives only)

This test is the load-bearing enforcement of the contract documented in
`src/a2web/packages/README.md`. If a package needs something from
`a2web.<domain>`, either move that thing into the package (because it's
infrastructure) or accept that the candidate isn't ready to be a package
yet (because it depends on domain).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGES_ROOT = _REPO_ROOT / "src" / "a2web" / "packages"

# Allowed prefixes for `from a2web.<x>` imports inside packages/.
_ALLOWED_A2WEB_PREFIXES: tuple[str, ...] = (
    "a2web.packages",
    "a2web.utils",
)


def _python_files_under(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _collect_a2web_imports(source: str) -> list[str]:
    """Return every `a2web.X` module path imported by `source`.

    Captures both `from a2web.x import y` and `import a2web.x`. Relative
    imports inside `packages/` resolve to `a2web.packages.*`, which is
    allowed — those don't appear in this list.
    """
    tree = ast.parse(source)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "a2web" or module.startswith("a2web."):
                out.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == "a2web" or name.startswith("a2web."):
                    out.append(name)
    return out


@pytest.mark.parametrize(
    "py_file",
    _python_files_under(_PACKAGES_ROOT),
    ids=lambda p: str(p.relative_to(_REPO_ROOT)),
)
def test_package_does_not_import_a2web_domain(py_file: Path) -> None:
    """Every module under packages/ stays clear of a2web domain imports."""
    source = py_file.read_text(encoding="utf-8")
    imports = _collect_a2web_imports(source)
    violations = [mod for mod in imports if not any(mod.startswith(prefix) for prefix in _ALLOWED_A2WEB_PREFIXES)]
    assert not violations, (
        f"{py_file.relative_to(_REPO_ROOT)} imports a2web domain module(s): "
        f"{violations}. Packages MUST stay infrastructure-only — boundary "
        "types belong inside the package. See packages/README.md."
    )


def test_packages_root_has_readme_and_init() -> None:
    """Sanity: the contract docs + init file exist."""
    assert (_PACKAGES_ROOT / "__init__.py").is_file()
    assert (_PACKAGES_ROOT / "README.md").is_file()
