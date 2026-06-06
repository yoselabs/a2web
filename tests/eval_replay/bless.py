"""Bless — write a curated `baseline/contract.json` from a replay.

Mirrors the existing `A2WEB_BLESS_CONTRACTS` golden-bless idiom: under
`A2WEB_BLESS_EVAL=1` a replay test (re)writes the deterministic baseline
instead of asserting it. The written contract is a *curated subset* of the
observed projection — the fields that are stable under replay and that we
want to assert — not a raw dump, so the baseline stays a readable,
reviewable statement of intent rather than a brittle snapshot.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval._capture.corpus import ReplayCase

BLESS_EVAL = os.environ.get("A2WEB_BLESS_EVAL") == "1"


def curate_contract(observed: dict[str, Any]) -> dict[str, Any]:
    """Build the asserted contract from an observed replay projection."""
    contract: dict[str, Any] = {
        "tier": observed["tier"],
        "status": observed["status"],
        "has_content": observed["has_content"],
    }
    if observed.get("answer_present"):
        contract["answer_present"] = True
        # Token cost is exact under LLM replay; assert an upper bound with a
        # little slack so a benign prompt-template tweak does not flap.
        contract["tokens_full_max"] = int(observed["tokens_full"]) + 50
    if observed.get("next_links_count", 0) > 0:
        contract["next_links_min"] = observed["next_links_count"]
    if observed.get("operator_hints"):
        contract["operator_hints"] = observed["operator_hints"]
    return contract


# Hand-authored *intent* keys — assertions about the projection, not observed
# values. Bless carries them forward verbatim so a re-bless never silently
# drops a case's acceptance gate.
_INTENT_KEYS = ("content_includes", "content_excludes", "answer_contains")


def bless_contract(case: ReplayCase, observed: dict[str, Any]) -> None:
    """Write the curated contract to the case's `baseline/contract.json`.

    Observed (shape) keys are recomputed from the replay; hand-authored intent
    keys (`content_includes`/`content_excludes`/`answer_contains`) are preserved
    from the prior baseline so a re-bless cannot drop an acceptance assertion.
    """
    baseline_dir = case.path / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    contract = curate_contract(observed)
    for key in _INTENT_KEYS:
        if key in case.baseline.contract:
            contract[key] = case.baseline.contract[key]
    (baseline_dir / "contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
