"""`make eval-refresh` — re-capture a case's inputs, diff, and (optionally) bless.

A site changes; its frozen `inputs/` drift. Refresh re-captures the live
world into `inputs/` (that layer is *meant* to drift) and then shows the
operator a **diff** of the freshly-produced answer against the committed
`baseline/answer.md`, alongside the deterministic `contract.json` diff.
The baseline is the asserted truth and is **never** overwritten without an
explicit bless (`A2WEB_BLESS_EVAL=1`), so a code-driven change can always
be told apart from a site-driven one before it is accepted.

Usage:

    make eval-refresh CASE=regression/some-slug
    A2WEB_BLESS_EVAL=1 make eval-refresh CASE=regression/some-slug   # accept the new baseline
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import sys
from pathlib import Path

from eval._capture.capture import _curate_contract, capture_case, write_baseline, write_inputs, write_meta
from eval._capture.corpus import load_case

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS_ROOT = _REPO_ROOT / "eval" / "corpus"


def _diff(label: str, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{label} (blessed)",
        tofile=f"{label} (fresh)",
    )
    return "".join(lines)


async def _run_refresh(case_ref: str) -> int:
    case_dir = _CORPUS_ROOT / case_ref
    if not (case_dir / "case.yaml").is_file():
        print(f"no such case: {case_ref} (expected {case_dir}/case.yaml)", file=sys.stderr)
        return 2

    corpus, _, slug = case_ref.partition("/")
    case = load_case(case_dir, corpus=corpus or "")
    bless = os.environ.get("A2WEB_BLESS_EVAL") == "1"

    print(f"re-capturing {case_ref} (live) …")
    artifacts = await capture_case(
        url=case.url,
        question=case.question,
        tags=case.tags,
        all_tiers=False,
    )

    # inputs/ is the drifting layer — always refreshed.
    write_inputs(case_dir, artifacts)
    write_meta(case_dir, case.url, artifacts)

    # baseline/ is the asserted layer — diffed, never silently overwritten.
    old_answer = case.baseline.answer or ""
    new_answer = (artifacts.response.extracted_answer or "").rstrip() + "\n" if artifacts.response.extracted_answer else ""
    old_contract = json.dumps(case.baseline.contract, indent=2, sort_keys=True) + "\n"
    new_contract = json.dumps(_curate_contract(artifacts.response), indent=2, sort_keys=True) + "\n"

    answer_diff = _diff("answer.md", old_answer, new_answer)
    contract_diff = _diff("contract.json", old_contract, new_contract)

    if not answer_diff and not contract_diff:
        print("no change vs blessed baseline — inputs refreshed, baseline unchanged.")
        return 0

    print("\n=== contract.json ===")
    print(contract_diff or "(unchanged)")
    print("\n=== answer.md ===")
    print(answer_diff or "(unchanged)")

    if bless:
        write_baseline(case_dir, artifacts.response)
        print(f"\nBLESSED — baseline updated for {case_ref}.")
        return 0

    print(f"\nNOT blessed. Review the diff above; accept with:\n  A2WEB_BLESS_EVAL=1 make eval-refresh CASE={case_ref}")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eval-refresh")
    p.add_argument("--case", required=True, help="corpus/slug, e.g. regression/hepsiburada-listing")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run_refresh(args.case))


if __name__ == "__main__":
    raise SystemExit(main())
