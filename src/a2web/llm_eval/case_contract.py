"""The per-case contract vocabulary — ONE implementation, two consumers.

Sibling of `contract.py`, and the distinction matters:

- `contract.py` checks the *envelope's own* field-presence rules. It is the
  same question for every case ("does this envelope obey v0.14?").
- this module checks *what a particular case expects* ("this URL is a wall, so
  `status` must be `failed` and `try_user_browser` must be in the hints").

The vocabulary was born in `tests/eval_replay/replay.py::assert_contract`,
where it is asserted offline against frozen bytes. `make bench` had no
equivalent: the live corpus could state its expectations only as `criteria`
prose for an LLM judge, so every deterministic fact a case knew about itself
(the tier that must win, the hint that must fire) was being scored by a model
at a cost, nondeterministically, or not at all.

Moving the checker here rather than importing it from `tests/` is not
bookkeeping — `src/` importing from `tests/` is backwards, and a second copy
would be worse: the two consumers would drift, and the whole point of a
contract vocabulary is that a key means the same thing wherever it is written.

**A key that cannot be checked in the current context is an ERROR, never a
pass.** The replay harness can observe things the live bench cannot (the
`steps` dispatch sequence, the extractor's `input_menu` — both come from the
cassette spy). If an unprojectable key silently succeeded, a case could carry
an assertion that reads as coverage while asserting nothing — the exact failure
this repo keeps finding. `unsupported` names them explicitly and the caller
decides.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Every key the vocabulary understands, and what it needs from `observed`.
#: Declared literally, for the same reason `wire._TSV_FIELDS` is literal:
#: deriving the supported set from whatever a projection happens to contain is
#: how a typo becomes a silently-skipped assertion.
CONTRACT_KEYS: frozenset[str] = frozenset(
    {
        "tier",
        "status",
        "has_content",
        "answer_present",
        "retrieval_incomplete",
        "narrative_present",
        "answer_contains",
        "tokens_full_max",
        "next_links_min",
        "operator_hints",
        "steps",
        "content_includes",
        "content_excludes",
        "input_menu_includes",
        "input_menu_excludes",
        "narrative_includes",
    }
)

#: Keys that need a cassette spy, so only the offline replay harness can check
#: them. `make bench` fetches live and has neither.
REPLAY_ONLY_KEYS: frozenset[str] = frozenset({"steps", "input_menu_includes", "input_menu_excludes"})

_EXACT = ("tier", "status")
_BOOL = ("has_content", "answer_present", "retrieval_incomplete", "narrative_present")


def check_contract_keys(
    contract: Mapping[str, Any],
    observed: Mapping[str, Any],
    *,
    supported: frozenset[str] = CONTRACT_KEYS,
) -> tuple[list[str], list[str]]:
    """Check `contract`'s blessed expectations against a projected `observed`.

    Args:
        contract: The case's expectations. Only keys present are checked.
        observed: A deterministic projection of the fetch (see `replay.observe`
            for the offline shape, `runner._observe_for_contract` for the live
            one). Both must use the same key names — that is the contract.
        supported: The keys this caller can actually evaluate. Defaults to the
            whole vocabulary; the live bench passes
            `CONTRACT_KEYS - REPLAY_ONLY_KEYS`.

    Returns:
        `(failures, unsupported)`. `failures` are assertions that ran and lost.
        `unsupported` are keys the caller cannot evaluate — reported separately
        because "I could not check this" and "this is wrong" are different
        facts, and collapsing them is how an unrunnable assertion comes to read
        as a passing one.
    """
    failures: list[str] = []
    unsupported: list[str] = []

    for key, expected in contract.items():
        if key not in CONTRACT_KEYS:
            failures.append(f"unknown contract key {key!r}")
            continue
        if key not in supported:
            unsupported.append(key)
            continue

        if key in _EXACT:
            if observed.get(key) != expected:
                failures.append(f"{key}: expected {expected!r}, got {observed.get(key)!r}")
        elif key in _BOOL:
            if bool(observed.get(key)) != bool(expected):
                failures.append(f"{key}: expected {bool(expected)}, got {bool(observed.get(key))}")
        elif key == "answer_contains":
            answer = observed.get("answer") or ""
            if str(expected) not in answer:
                failures.append(f"answer_contains: {expected!r} not in answer {answer[:120]!r}")
        elif key == "tokens_full_max":
            if observed.get("tokens_full", 0) > expected:
                failures.append(f"tokens_full_max: {observed.get('tokens_full')} > {expected}")
        elif key == "next_links_min":
            if observed.get("next_links_count", 0) < expected:
                failures.append(f"next_links_min: {observed.get('next_links_count')} < {expected}")
        elif key == "operator_hints":
            if observed.get("operator_hints") != list(expected):
                failures.append(f"operator_hints: expected {expected!r}, got {observed.get('operator_hints')!r}")
        elif key == "steps":
            if observed.get("steps") != list(expected):
                failures.append(
                    f"steps: the tier dispatch sequence changed — expected {expected!r}, got {observed.get('steps')!r}. "
                    "This is the planner's outcome-level witness: a routing rule fired differently. "
                    "Confirm the new sequence is intended before re-blessing."
                )
        elif key in ("content_includes", "content_excludes"):
            failures.extend(_substrings(observed.get("content_md") or "", key, expected, "projected content"))
        elif key in ("input_menu_includes", "input_menu_excludes"):
            failures.extend(_substrings(observed.get("input_menu") or "", key, expected, "the content fed to the extractor"))
        elif key == "narrative_includes":
            failures.extend(_substrings(observed.get("narrative") or "", key, expected, "narrative"))

    return failures, unsupported


def _substrings(haystack: str, key: str, expected: Any, what: str) -> list[str]:
    """Shared include/exclude body. The four include/exclude pairs differed only
    in their message, and one of them (`content_excludes`) said "fused/forbidden"
    while its sibling said "forbidden" — a wording drift that is exactly what
    happens when the same check is written four times."""
    want_present = key.endswith("_includes")
    out: list[str] = []
    for needle in expected:
        if (str(needle) in haystack) is not want_present:
            verb = "not in" if want_present else "unexpectedly present in"
            out.append(f"{key}: {needle!r} {verb} {what}")
    return out


__all__ = ["CONTRACT_KEYS", "REPLAY_ONLY_KEYS", "check_contract_keys"]
