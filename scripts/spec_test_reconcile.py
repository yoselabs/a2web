#!/usr/bin/env python3
"""Reconcile openspec requirements against the test suite.

Read-only report by default. Two columns matter:

  * requirement with no test  -> an UNVERIFIED requirement (the risky column)
  * test with no citation     -> an UNJUSTIFIED example

Citation forms recognised:
  * loose (heuristic, pre-existing): directory alignment
    (tests/capabilities/<cap> <-> openspec/specs/<cap>), an ADR id anywhere in
    the file (ADR-00NN), or a "Requirement:" heading quoted in the file text.
  * marker (structured, openspec/changes/bind-tests-to-requirements):
    ``@pytest.mark.protects("spec:<capability>", "Requirement: <heading>")``,
    ``@pytest.mark.protects("adr:<NNNN>")``, or
    ``@pytest.mark.protects("change:<change-id>")``. Collected by AST, not
    regex, so a marker name inside a docstring or fixture is never mistaken
    for a real declaration. An id that does not resolve is reported as a
    defect, distinct from the baseline columns.

``--check`` asserts the marker-based traceable-requirement count has not
dropped below the committed floor (``TRACEABLE_REQUIREMENTS_FLOOR`` below)
and that every declared marker resolves. See
openspec/specs/spec-test-traceability/spec.md.

Usage:  uv run python scripts/spec_test_reconcile.py [--json] [--check]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Monotone floor for spec-test-traceability (openspec/changes/bind-tests-to-requirements).
# Committed literal, not derived at runtime (design.md D4) — a floor computed
# from the suite it constrains can only ever report that the suite equals
# itself. Raising this is an ordinary edit accompanying the change that
# earned it. Lowering it requires a stated reason recorded right here; the
# only legitimate reason is a requirement being deliberately removed from a
# spec (openspec/specs/spec-test-traceability/spec.md, "Traceability is a
# monotone floor"). Set 2026-08-06 to the count measured after seeding the
# first markers (task 5 of the change's tasks.md).
TRACEABLE_REQUIREMENTS_FLOOR = 1
SPECS = ROOT / "openspec" / "specs"
TESTS = ROOT / "tests"
ADRS = ROOT / "docs" / "adr"
CHANGES = ROOT / "openspec" / "changes"

REQ_RE = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.M)
SCEN_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$", re.M)
TEST_RE = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.M)
ADR_RE = re.compile(r"ADR-(\d{4})")


@dataclass
class Capability:
    name: str
    requirements: list[str] = field(default_factory=list)
    scenarios: int = 0
    test_dir: Path | None = None
    tests: int = 0
    cited_requirements: set[str] = field(default_factory=set)


@dataclass
class Marker:
    file: str
    test: str
    kind: str  # "spec" | "adr" | "change"
    ref: str  # capability, ADR id, or change id
    heading: str | None = None  # requirement heading, for kind == "spec"


def load_specs() -> dict[str, Capability]:
    caps: dict[str, Capability] = {}
    for spec in sorted(SPECS.glob("*/spec.md")):
        name = spec.parent.name
        text = spec.read_text(encoding="utf-8")
        caps[name] = Capability(
            name=name,
            requirements=REQ_RE.findall(text),
            scenarios=len(SCEN_RE.findall(text)),
        )
    return caps


def test_files() -> list[Path]:
    return [p for p in TESTS.rglob("test_*.py") if "__pycache__" not in p.parts]


def _protects_args(call: ast.Call) -> list[str]:
    return [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _is_protects_call(node: ast.expr) -> ast.Call | None:
    call = node
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    # pytest.mark.protects(...)
    if isinstance(func, ast.Attribute) and func.attr == "protects" and isinstance(func.value, ast.Attribute) and func.value.attr == "mark":
        return call
    return None


def collect_markers(files: list[Path]) -> list[Marker]:
    markers: list[Marker] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        rel = str(f.relative_to(ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            for dec in node.decorator_list:
                call = _is_protects_call(dec)
                if call is None:
                    continue
                args = _protects_args(call)
                if not args:
                    continue
                head, *rest = args
                if ":" not in head:
                    continue
                kind, ref = head.split(":", 1)
                if kind == "spec":
                    heading = rest[0] if rest else ""
                    markers.append(Marker(rel, node.name, "spec", ref, heading))
                elif kind in {"adr", "change"}:
                    markers.append(Marker(rel, node.name, kind, ref))
    return markers


def resolve_markers(markers: list[Marker], caps: dict[str, Capability], all_adrs: set[str]) -> dict:
    resolved_requirements: set[tuple[str, str]] = set()
    resolved_adrs: set[str] = set()
    resolved_changes: set[str] = set()
    witnesses: set[str] = set()
    unresolved: list[dict] = []

    change_ids = {p.name for p in CHANGES.iterdir() if p.is_dir() and p.name != "archive"}
    if (CHANGES / "archive").is_dir():
        change_ids |= {p.name for p in (CHANGES / "archive").iterdir() if p.is_dir()}

    def norm(s: str) -> str:
        s = " ".join(s.split())
        if s.lower().startswith("requirement:"):
            s = s[len("requirement:") :].strip()
        return s

    for m in markers:
        if m.kind == "spec":
            cap = caps.get(m.ref)
            heading = norm(m.heading or "")
            match = cap and any(norm(r) == heading for r in cap.requirements)
            if cap and match:
                resolved_requirements.add((m.ref, heading))
            else:
                unresolved.append({"file": m.file, "test": m.test, "kind": "spec", "ref": f"{m.ref}::{m.heading}"})
        elif m.kind == "adr":
            if m.ref in all_adrs:
                resolved_adrs.add(m.ref)
            else:
                unresolved.append({"file": m.file, "test": m.test, "kind": "adr", "ref": m.ref})
        elif m.kind == "change":
            if m.ref in change_ids:
                resolved_changes.add(m.ref)
                witnesses.add(f"{m.file}::{m.test}")
            else:
                unresolved.append({"file": m.file, "test": m.test, "kind": "change", "ref": m.ref})

    return {
        "total_markers": len(markers),
        "resolved_requirements": sorted(f"{c}::{h}" for c, h in resolved_requirements),
        "resolved_adrs": sorted(resolved_adrs),
        "resolved_changes": sorted(resolved_changes),
        "regression_witnesses": sorted(witnesses),
        "unresolved": unresolved,
    }


def reconcile() -> dict:
    caps = load_specs()
    files = test_files()

    # directory alignment: any tests/**/<snake> dir matching the capability name
    for cap in caps.values():
        snake = cap.name.replace("-", "_")
        for base in (TESTS / "capabilities" / snake, TESTS / snake):
            if base.is_dir():
                cap.test_dir = base
                break
        else:
            match = [d for d in TESTS.rglob(snake) if d.is_dir() and "__pycache__" not in d.parts]
            if match:
                cap.test_dir = match[0]

    total_tests = 0
    cited_by_adr: dict[str, set[str]] = defaultdict(set)
    uncited: list[tuple[str, int]] = []
    quoted_reqs: set[str] = set()
    req_index = {r: c.name for c in caps.values() for r in c.requirements}

    for f in files:
        text = f.read_text(encoding="utf-8")
        n = len(TEST_RE.findall(text))
        total_tests += n
        rel = str(f.relative_to(ROOT))

        adrs = set(ADR_RE.findall(text))
        for a in adrs:
            cited_by_adr[a].add(rel)

        hit_req = {r for r in req_index if r and r in text}
        quoted_reqs |= hit_req

        in_cap_dir = any(c.test_dir and c.test_dir in f.parents for c in caps.values())
        if not (adrs or hit_req or in_cap_dir):
            uncited.append((rel, n))

    # ADRs that exist but no test cites
    all_adrs = {p.name[:4] for p in ADRS.glob("[0-9]*.md")}
    uncited_adrs = sorted(all_adrs - set(cited_by_adr))

    for cap in caps.values():
        if cap.test_dir:
            cap.tests = sum(len(TEST_RE.findall(p.read_text(encoding="utf-8"))) for p in cap.test_dir.rglob("test_*.py"))
        cap.cited_requirements = {r for r in cap.requirements if r in quoted_reqs}

    unverified = [c for c in caps.values() if c.test_dir is None]
    total_reqs = sum(len(c.requirements) for c in caps.values())
    total_scen = sum(c.scenarios for c in caps.values())

    markers = collect_markers(files)
    marker_report = resolve_markers(markers, caps, all_adrs)

    return {
        "totals": {
            "capabilities": len(caps),
            "requirements": total_reqs,
            "scenarios": total_scen,
            "test_files": len(files),
            "tests": total_tests,
            "requirements_quoted_by_a_test": len(quoted_reqs),
            "capabilities_without_test_dir": len(unverified),
            "adrs": len(all_adrs),
            "adrs_cited": len(cited_by_adr),
            "requirements_traceable_by_marker": len(marker_report["resolved_requirements"]),
            "floor": TRACEABLE_REQUIREMENTS_FLOOR,
        },
        "capabilities": [
            {
                "name": c.name,
                "requirements": len(c.requirements),
                "scenarios": c.scenarios,
                "tests": c.tests,
                "test_dir": str(c.test_dir.relative_to(ROOT)) if c.test_dir else None,
                "requirements_cited": len(c.cited_requirements),
            }
            for c in sorted(caps.values(), key=lambda c: -len(c.requirements))
        ],
        "unverified_capabilities": sorted(c.name for c in unverified),
        "uncited_adrs": uncited_adrs,
        "uncited_test_files": sorted(uncited, key=lambda t: -t[1]),
        "markers": marker_report,
    }


def _print_unresolved(unresolved: list[dict], *, prefix: str = "") -> None:
    for u in unresolved:
        print(f"{prefix}{u['kind']:<6} {u['ref']:<40} {u['file']}::{u['test']}")


def render(rep: dict) -> None:
    t = rep["totals"]
    print("SPEC <-> TEST RECONCILIATION\n")
    print(f"  capabilities            {t['capabilities']:>6}")
    print(f"  requirements            {t['requirements']:>6}")
    print(f"  scenarios               {t['scenarios']:>6}")
    print(f"  tests                   {t['tests']:>6}  ({t['test_files']} files)")
    print()
    print("COLUMN A - requirements with no LOCATABLE evidence (the risky column)")
    print("  NOTE: 'no test dir' means unlocatable, NOT untested. Verified by")
    print("  spot-check: proxy-pool IS tested, filed under tier_pipeline. That")
    print("  ambiguity is the defect - the edge is missing, so you cannot tell.")
    print(f"  capabilities with NO test dir     {t['capabilities_without_test_dir']:>4} / {t['capabilities']}")
    print(f"  requirements quoted by any test   {t['requirements_quoted_by_a_test']:>4} / {t['requirements']}")
    for n in rep["unverified_capabilities"]:
        print(f"    - {n}")
    print()
    print("COLUMN B - unjustified tests (no ADR, no requirement, no capability dir)")
    uncited = rep["uncited_test_files"]
    print(f"  files {len(uncited)} / {t['test_files']}   tests {sum(n for _, n in uncited)} / {t['tests']}")
    for path, n in uncited[:20]:
        print(f"    {n:>4}  {path}")
    if len(uncited) > 20:
        print(f"    ... {len(uncited) - 20} more")
    print()
    print(f"ADRs: {t['adrs_cited']}/{t['adrs']} cited by a test")
    if rep["uncited_adrs"]:
        print(f"  never cited: {', '.join(rep['uncited_adrs'])}")
    print()
    m = rep["markers"]
    print(f"MARKERS (@pytest.mark.protects) - {m['total_markers']} declared")
    print(f"  requirements traceable by marker  {t['requirements_traceable_by_marker']:>4}   (floor {t['floor']})")
    print(f"  ADRs cited by marker              {len(m['resolved_adrs']):>4}")
    print(f"  regression witnesses (change:)    {len(m['regression_witnesses']):>4}")
    if m["unresolved"]:
        print(f"  UNRESOLVED ({len(m['unresolved'])}) - a declared id that does not exist:")
        _print_unresolved(m["unresolved"], prefix="    ")
    print()
    print("PER-CAPABILITY  (req / scen / tests / reqs-quoted)")
    for c in rep["capabilities"]:
        flag = "" if c["test_dir"] else "   <- NO TEST DIR"
        print(f"  {c['name']:<34} {c['requirements']:>4} {c['scenarios']:>5} {c['tests']:>6} {c['requirements_cited']:>6}{flag}")


def check(rep: dict) -> int:
    """Non-zero on: any unresolved marker, or traceable count below the floor."""
    m = rep["markers"]
    t = rep["totals"]
    ok = True

    if m["unresolved"]:
        print(f"FAIL: {len(m['unresolved'])} protects marker(s) do not resolve:")
        _print_unresolved(m["unresolved"], prefix="  ")
        ok = False

    traceable = t["requirements_traceable_by_marker"]
    floor = t["floor"]
    if traceable < floor:
        print(f"FAIL: traceable requirements dropped: {traceable} < floor {floor}")
        ok = False
    elif traceable > floor:
        print(f"OK: traceable requirements {traceable} > floor {floor} — floor may be raised in this change")
    else:
        print(f"OK: traceable requirements {traceable} == floor {floor}")

    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit non-zero on regression or unresolved markers")
    args = ap.parse_args()
    rep = reconcile()
    if args.check:
        return check(rep)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        render(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
