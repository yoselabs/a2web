#!/usr/bin/env python3
"""Reconcile openspec requirements against the test suite.

Read-only report, not a gate. Two columns matter:

  * requirement with no test  -> an UNVERIFIED requirement (the risky column)
  * test with no citation     -> an UNJUSTIFIED example

Citation forms recognised today (Stage 1 markers do not exist yet):
  * directory alignment: tests/capabilities/<cap> <-> openspec/specs/<cap>
  * an ADR id in the test file (ADR-00NN)
  * an explicit "Requirement:" heading quoted in the test file

Usage:  uv run python scripts/spec_test_reconcile.py [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "openspec" / "specs"
TESTS = ROOT / "tests"
ADRS = ROOT / "docs" / "adr"

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
    }


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
    print("PER-CAPABILITY  (req / scen / tests / reqs-quoted)")
    for c in rep["capabilities"]:
        flag = "" if c["test_dir"] else "   <- NO TEST DIR"
        print(f"  {c['name']:<34} {c['requirements']:>4} {c['scenarios']:>5} {c['tests']:>6} {c['requirements_cited']:>6}{flag}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = reconcile()
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        render(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
