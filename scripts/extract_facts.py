#!/usr/bin/env python
"""extract_facts.py — emit curated codebase facts as JSON for Rego policies.

Walks Python sources, parses each with stdlib ``ast``, and emits a single
JSON document conforming to the schema printable via ``--schema``.

The extractor is a pure function of its input tree: same tree → same JSON,
byte-for-byte. No clock reads, no env reads, no network. Used as the
fact-substrate for ``policies/*.rego``; consumed by ``a2kit lint rego``.

**ast_hash_normalized strategy** (used by ``body_dup.rego``):

Each function's body subtree is normalized:
- ``ast.Name(id=...)`` → ``ast.Name(id="_ID_")``
- ``ast.arg(arg=..., annotation=...)`` → ``ast.arg(arg="_ID_", annotation=None)``
- ``ast.Attribute(attr=...)`` → ``ast.Attribute(attr="_ID_")``
- ``ast.Constant(value=<str|int|float|bytes>)`` → ``ast.Constant(value="_LIT_")``
  (``None`` / ``True`` / ``False`` / ``...`` preserved — semantic distinction)
- ``ast.AnnAssign.annotation`` collapsed to ``_LIT_``
- ``decorator_list`` stripped (decorators are signature, not body)
- ``returns`` stripped (return annotation is signature)

Hash is SHA-256 of ``ast.dump(...)`` of the normalized body module. Two
functions with the same body shape (modulo identifier and literal names)
produce the same hash; functions with different operators / control flow
produce different hashes.

Examples that hash *equal*::

    def f(x): return x + 1
    def g(y): return y + 1       # identifier name differs
    def h(a): return a + 99      # literal value differs

Examples that hash *different*::

    def f(x): return x + 1
    def g(x): return x * 2       # different operator
    def h(x):                    # extra statement
        y = x + 1
        return y

**noqa grammar** (matches ``packages/lint/static.py:parse_noqa``,
commit 83819db):

  ``# noqa: <CODE>[, <CODE>]* [-- <reason text>]``

The separator is exactly ``" -- "`` (space-dash-dash-space). The reason is
free text after.

**REGO-* rules upgrade the convention to required.** A bare ``# noqa:
REGO-*`` without a ``" -- "`` reason raises ``NoqaError`` and the
extractor exits non-zero. Rego policies enforce architectural invariants;
every suppression must be justified inline. A2K-* rules retain the
existing tolerance (reason is conventional, not enforced).
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SENTINEL_ID = "_ID_"
SENTINEL_LIT = "_LIT_"

NOQA_PREFIX = "# noqa"
NOQA_REASON_SEP = " -- "
REGO_RULE_PREFIX = "REGO-"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_UPPER_BOUND_RE = re.compile(r"(<=|<|~=)")
_REQ_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+")


SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["functions", "modules", "suppressions", "workflows", "pyproject"],
    "properties": {
        "functions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "file",
                    "name",
                    "line",
                    "kind",
                    "is_async",
                    "is_private",
                    "is_dunder",
                    "body_stmt_count",
                    "ast_hash_normalized",
                ],
                "properties": {
                    "file": {"type": "string"},
                    "name": {"type": "string"},
                    "line": {"type": "integer"},
                    "kind": {
                        "type": "string",
                        "enum": ["function", "method", "classmethod", "staticmethod"],
                    },
                    "is_async": {"type": "boolean"},
                    "is_private": {"type": "boolean"},
                    "is_dunder": {"type": "boolean"},
                    "body_stmt_count": {"type": "integer"},
                    "ast_hash_normalized": {"type": "string"},
                },
            },
        },
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "has_module_getattr"],
                "properties": {
                    "file": {"type": "string"},
                    "has_module_getattr": {"type": "boolean"},
                },
            },
        },
        "suppressions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "line", "rule_id", "reason"],
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "rule_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "workflows": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "name", "permissions", "on", "jobs"],
                "properties": {
                    "file": {"type": "string"},
                    "name": {"type": ["string", "null"]},
                    "permissions": {"type": ["object", "string", "null"]},
                    "on": {"type": ["array", "object", "string"]},
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "permissions", "steps"],
                            "properties": {
                                "name": {"type": "string"},
                                "permissions": {"type": ["object", "string", "null"]},
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["uses", "uses_ref", "has_pinned_sha", "vendor", "with_keys"],
                                        "properties": {
                                            "uses": {"type": ["string", "null"]},
                                            "uses_ref": {"type": ["string", "null"]},
                                            "has_pinned_sha": {"type": "boolean"},
                                            "vendor": {"type": ["string", "null"]},
                                            "with_keys": {"type": "array", "items": {"type": "string"}},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "pyproject": {
            "type": "object",
            "required": ["dependencies", "optional_dependencies", "build_system_requires"],
            "properties": {
                "dependencies": {"type": "array"},
                "optional_dependencies": {"type": "object"},
                "build_system_requires": {"type": "array"},
            },
        },
    },
}


class NoqaError(Exception):
    """REGO-* noqa missing the required ` -- <reason>` suffix."""


# --------------------------------------------------------------------------- #
# AST normalization for body hashing
# --------------------------------------------------------------------------- #


class _Normalizer(ast.NodeTransformer):
    """Replace identifiers + literals with sentinels for body hashing."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.Name(id=SENTINEL_ID, ctx=node.ctx)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: ARG002 -- NodeTransformer interface; we discard the input and return a fresh sentinel node
        return ast.arg(arg=SENTINEL_ID, annotation=None)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        return ast.Attribute(value=node.value, attr=SENTINEL_ID, ctx=node.ctx)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # None / True / False / Ellipsis are semantic; preserve them
        if node.value is None or isinstance(node.value, bool) or node.value is Ellipsis:
            return node
        return ast.Constant(value=SENTINEL_LIT)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        self.generic_visit(node)
        return ast.AnnAssign(
            target=node.target,
            annotation=ast.Constant(value=SENTINEL_LIT),
            value=node.value,
            simple=node.simple,
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return ast.FunctionDef(
            name=SENTINEL_ID,
            args=node.args,
            body=node.body,
            decorator_list=[],
            returns=None,
            type_params=getattr(node, "type_params", []),
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        return ast.AsyncFunctionDef(
            name=SENTINEL_ID,
            args=node.args,
            body=node.body,
            decorator_list=[],
            returns=None,
            type_params=getattr(node, "type_params", []),
        )


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop the leading docstring statement if present.

    Two functions with identical logic but different docstring presence
    SHALL hash equal — docstrings are documentation, not behavior.
    """
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, (str, bytes)):
        return body[1:]
    return body


def _count_stmts(body: list[ast.stmt]) -> int:
    """Count statements recursively.

    A single ``try`` block with 5 nested statements counts as 6, not 1.
    The body_dup floor filters trivial 1-2 statement collisions
    (``return x``, ``raise X``); we want substantial bodies wherever
    they're shaped, including nested ones. Top-level stmt counting would
    filter R2 (``resolve_hints`` — single try/except with substantial
    body) as a 1-stmt function, which is wrong for our purposes.
    """
    total = 0
    for stmt in body:
        for _ in ast.walk(stmt):
            # ast.walk yields every node; count only Stmt subtypes
            total += 1 if isinstance(_, ast.stmt) else 0
    return total


def ast_hash_normalized(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """SHA-256 of the function body with identifiers + literals normalized.

    Deep-copies the body before normalizing — the NodeTransformer would
    otherwise mutate the original tree, stripping ``lineno`` from nested
    function definitions and breaking subsequent walks.
    """
    body = _strip_docstring([copy.deepcopy(stmt) for stmt in fn.body])
    normalizer = _Normalizer()
    normalized_body = [normalizer.visit(stmt) for stmt in body]
    body_module = ast.Module(body=normalized_body, type_ignores=[])
    dumped = ast.dump(body_module, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Function / module / suppression extraction
# --------------------------------------------------------------------------- #


def _function_kind(fn: ast.FunctionDef | ast.AsyncFunctionDef, parent: ast.AST | None) -> str:
    if not isinstance(parent, ast.ClassDef):
        return "function"
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Name):
            if dec.id == "staticmethod":
                return "staticmethod"
            if dec.id == "classmethod":
                return "classmethod"
    return "method"


def extract_functions(tree: ast.Module, filepath: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(node: ast.AST, parent: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                is_dunder = name.startswith("__") and name.endswith("__")
                is_private = name.startswith("_") and not is_dunder
                body_stmts = _strip_docstring(child.body)
                out.append(
                    {
                        "file": filepath,
                        "name": name,
                        "line": child.lineno,
                        "kind": _function_kind(child, parent),
                        "is_async": isinstance(child, ast.AsyncFunctionDef),
                        "is_private": is_private,
                        "is_dunder": is_dunder,
                        "body_stmt_count": _count_stmts(body_stmts),
                        "ast_hash_normalized": ast_hash_normalized(child),
                    }
                )
            walk(child, node)

    walk(tree, None)
    return out


def extract_module(tree: ast.Module, filepath: str) -> dict[str, Any]:
    has_module_getattr = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            has_module_getattr = True
            break
    return {"file": filepath, "has_module_getattr": has_module_getattr}


def extract_suppressions(source: str, filepath: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        idx = line.find(NOQA_PREFIX)
        if idx == -1:
            continue
        rest = line[idx + len(NOQA_PREFIX) :].lstrip()
        if not rest.startswith(":"):
            # Bare wildcard form (no colon, no codes) — REGO rules don't accept wildcards.
            continue
        payload = rest[1:]
        reason_idx = payload.find(NOQA_REASON_SEP)
        if reason_idx == -1:
            codes_str = payload
            reason = ""
        else:
            codes_str = payload[:reason_idx]
            reason = payload[reason_idx + len(NOQA_REASON_SEP) :].strip()
        codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        for code in codes:
            if code.startswith(REGO_RULE_PREFIX) and not reason:
                raise NoqaError(
                    f"{filepath}:{lineno}: # noqa: {code} requires a reason "
                    f"(grammar: `# noqa: {code} -- <why>`). "
                    f"REGO-* rules enforce architectural invariants — "
                    f"every suppression must be justified inline."
                )
            out.append({"file": filepath, "line": lineno, "rule_id": code, "reason": reason})
    return out


# --------------------------------------------------------------------------- #
# Workflow facts (.github/workflows/*.yml)
# --------------------------------------------------------------------------- #


def _step_facts(step: dict[str, Any]) -> dict[str, Any]:
    uses = step.get("uses")
    if not isinstance(uses, str):
        return {
            "uses": None,
            "uses_ref": None,
            "has_pinned_sha": False,
            "vendor": None,
            "with_keys": sorted((step.get("with") or {}).keys()) if isinstance(step.get("with"), dict) else [],
        }
    name, _, ref = uses.partition("@")
    vendor, _, _rest = name.partition("/")
    ref = ref or ""
    return {
        "uses": uses,
        "uses_ref": ref or None,
        "has_pinned_sha": bool(_SHA_RE.match(ref)),
        "vendor": vendor or None,
        "with_keys": sorted((step.get("with") or {}).keys()) if isinstance(step.get("with"), dict) else [],
    }


def _job_facts(job_name: str, job: dict[str, Any]) -> dict[str, Any]:
    steps_raw = job.get("steps") or []
    steps = [_step_facts(s) for s in steps_raw if isinstance(s, dict)]
    permissions = job.get("permissions")
    return {"name": job_name, "permissions": permissions, "steps": steps}


def _workflow_facts(path: Path, doc: dict[str, Any]) -> dict[str, Any]:
    jobs_raw = doc.get("jobs") or {}
    jobs = [_job_facts(str(name), job) for name, job in sorted(jobs_raw.items()) if isinstance(job, dict)]
    return {
        "file": str(path),
        "name": doc.get("name") if isinstance(doc.get("name"), str) else None,
        "permissions": doc.get("permissions"),
        "on": doc.get("on") if doc.get("on") is not None else [],
        "jobs": jobs,
    }


def extract_workflows(repo_root: Path) -> list[dict[str, Any]]:
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        out.append(_workflow_facts(path.relative_to(repo_root), doc))
    out.sort(key=lambda d: d["file"])
    return out


# --------------------------------------------------------------------------- #
# pyproject facts
# --------------------------------------------------------------------------- #


def _parse_requirement(spec: str) -> dict[str, Any]:
    """Parse a PEP 508 requirement (best-effort, name + raw spec + upper-bound flag).

    Full PEP 508 parsing would require `packaging`; we extract just enough to
    answer "does this carry an upper bound?". Markers / extras / URLs are
    preserved in the raw `spec` field for human reading but not interpreted.
    """
    raw = spec.strip()
    match = _REQ_NAME_RE.match(raw)
    name = match.group(0) if match else raw
    rest = raw[len(name) :]
    # Strip extras like `[test]` from the version-spec scan
    version_part = rest
    if version_part.startswith("["):
        end = version_part.find("]")
        if end != -1:
            version_part = version_part[end + 1 :]
    # Strip env-markers (`; python_version >= "3.11"`); only the dep-spec carries upper bounds
    if ";" in version_part:
        version_part = version_part.split(";", 1)[0]
    has_upper = bool(_UPPER_BOUND_RE.search(version_part))
    return {"name": name, "spec": raw, "has_upper_bound": has_upper}


def extract_pyproject(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "pyproject.toml"
    empty = {"dependencies": [], "optional_dependencies": {}, "build_system_requires": []}
    if not path.is_file():
        return empty
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return empty
    project = doc.get("project") or {}
    deps = [_parse_requirement(s) for s in (project.get("dependencies") or []) if isinstance(s, str)]
    opt: dict[str, list[dict[str, Any]]] = {}
    for group, specs in (project.get("optional-dependencies") or {}).items():
        if isinstance(specs, list):
            opt[group] = [_parse_requirement(s) for s in specs if isinstance(s, str)]
    bsr = [_parse_requirement(s) for s in ((doc.get("build-system") or {}).get("requires") or []) if isinstance(s, str)]
    return {"dependencies": deps, "optional_dependencies": opt, "build_system_requires": bsr}


# --------------------------------------------------------------------------- #
# Walk + entrypoint
# --------------------------------------------------------------------------- #


def walk_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            out.append(p)
    return out


def extract(paths: list[Path], repo_root: Path | None = None) -> dict[str, Any]:
    files = walk_paths(paths)
    functions: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    suppressions: list[dict[str, Any]] = []

    for filepath in files:
        if filepath.name == "extract_facts.py":
            continue
        if "__pycache__" in filepath.parts:
            continue
        try:
            source = filepath.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            continue
        rel = str(filepath)
        functions.extend(extract_functions(tree, rel))
        modules.append(extract_module(tree, rel))
        suppressions.extend(extract_suppressions(source, rel))

    functions.sort(key=lambda d: (d["file"], d["line"], d["name"]))
    modules.sort(key=lambda d: d["file"])
    suppressions.sort(key=lambda d: (d["file"], d["line"], d["rule_id"]))

    root = repo_root if repo_root is not None else Path.cwd()
    workflows = extract_workflows(root)
    pyproject = extract_pyproject(root)

    return {
        "functions": functions,
        "modules": modules,
        "suppressions": suppressions,
        "workflows": workflows,
        "pyproject": pyproject,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_facts.py",
        description="Walk Python sources and emit curated facts as JSON for Rego policies.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["src/"],
        help="Paths to walk (default: src/).",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the JSON schema of the output and exit.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output path (default: - for stdout).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root for workflow + pyproject collections (default: cwd).",
    )
    args = parser.parse_args(argv)

    if args.schema:
        json.dump(SCHEMA, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    paths = [Path(p) for p in args.paths]
    repo_root = Path(args.repo_root) if args.repo_root else None
    try:
        facts = extract(paths, repo_root=repo_root)
    except NoqaError as e:
        print(f"extract_facts.py: error: {e}", file=sys.stderr)
        return 2

    text = json.dumps(facts, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
