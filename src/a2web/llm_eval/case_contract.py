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

import re
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
        "answer_excludes",
        "operator_hints_include",
        "operator_hints_exclude",
        "hint_severity",
        "confidence_max",
        "other_pages_min",
        "other_pages_kinds",
        "other_pages_all_have_anchor",
        "options_min",
        "options_max",
        "options_all_have_url",
        "also_here_min",
        "index_non_empty",
        "answer_urls_traceable",
    }
)

#: Keys that need a cassette spy, so only the offline replay harness can check
#: them. `make bench` fetches live and has neither.
REPLAY_ONLY_KEYS: frozenset[str] = frozenset({"steps", "input_menu_includes", "input_menu_excludes"})

#: The mirror set: keys only the LIVE bench can check.
#:
#: Offline replay drives `fetch()` and projects a `FetchResponse` — the
#: page-shaped `fetch_raw` envelope, which has `next_links` and no
#: `other_pages` / `options` / `also_here` at all. Those are `AskResponse`
#: fields, and `AskResponse` is what `a2web_extract` puts on the bench.
#: `hint_severity` and `confidence_max` are here for a smaller reason: the live
#: envelope already carries both, and adding them to `replay.observe` would
#: require re-blessing every baseline — a real cost, and not one this group
#: needs to pay to convert the criteria that are actually dead.
#:
#: Declared as a set rather than left implicit for the same reason
#: `REPLAY_ONLY_KEYS` is: a key one harness cannot evaluate must come back
#: `unsupported`, never silently pass.
BENCH_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "hint_severity",
        "confidence_max",
        "other_pages_min",
        "other_pages_kinds",
        "other_pages_all_have_anchor",
        "options_min",
        "options_max",
        "options_all_have_url",
        "also_here_min",
        "index_non_empty",
    }
)

_EXACT = ("tier", "status")
_BOOL = ("has_content", "answer_present", "retrieval_incomplete", "narrative_present")

#: `confidence` is an ordered enum on the wire; `confidence_max` needs the order.
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

#: An http(s) URL inside prose. Trailing sentence punctuation is excluded from
#: the match rather than stripped afterwards, so `see https://x/a.` yields
#: `https://x/a` and not a URL that exists nowhere.
_URL_IN_PROSE = re.compile(r"https?://[^\s<>\)\]\"'`]+")
_URL_TRAILING = ".,;:!?"


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
        elif key == "answer_excludes":
            failures.extend(_substrings(observed.get("answer") or "", key, expected, "answer"))
        elif key == "operator_hints_include":
            fired = set(observed.get("operator_hints") or ())
            failures.extend(
                f"operator_hints_include: {code!r} did not fire (fired: {sorted(fired)})"
                for code in expected
                if code not in fired
            )
        elif key == "operator_hints_exclude":
            fired = set(observed.get("operator_hints") or ())
            failures.extend(
                f"operator_hints_exclude: {code!r} fired and must not" for code in expected if code in fired
            )
        elif key == "hint_severity":
            failures.extend(_check_severity(observed, expected))
        elif key == "confidence_max":
            failures.extend(_check_confidence_max(observed, expected))
        elif key == "answer_urls_traceable":
            failures.extend(_check_answer_urls(observed, expected))
        else:
            failures.extend(_check_index(key, expected, observed))

    return failures, unsupported


def _check_severity(observed: Mapping[str, Any], expected: Any) -> list[str]:
    """`{code: severity}` — the hint fired AND carries that severity.

    Both halves matter and the second is the one that has actually broken:
    ADR-0009's `try_user_browser` reached the agent unmarked for weeks because a
    quieter hint preceded it in the TSV table. A case that pins only the code
    would have stayed green through that.
    """
    severities = observed.get("hint_severities") or {}
    out: list[str] = []
    for code, want in expected.items():
        if code not in severities:
            out.append(f"hint_severity: {code!r} did not fire at all (fired: {sorted(severities)})")
        elif severities[code] != want:
            out.append(f"hint_severity: {code!r} is {severities[code]!r}, expected {want!r}")
    return out


def _check_confidence_max(observed: Mapping[str, Any], expected: Any) -> list[str]:
    """A ceiling, not equality — the envelope must not claim MORE confidence
    than the case allows. `dead-product-url-fat-404` is the shape: a response
    describing a page as missing must not simultaneously report `high`."""
    got = observed.get("confidence")
    if got not in _CONFIDENCE_RANK:
        return [f"confidence_max: cannot read confidence from the envelope (got {got!r})"]
    if expected not in _CONFIDENCE_RANK:
        return [f"confidence_max: {expected!r} is not one of {sorted(_CONFIDENCE_RANK)}"]
    if _CONFIDENCE_RANK[got] > _CONFIDENCE_RANK[expected]:
        return [f"confidence_max: envelope claims {got!r}, ceiling is {expected!r}"]
    return []


def _check_answer_urls(observed: Mapping[str, Any], expected: Any) -> list[str]:
    """**ADR-0014, deterministically — the invariant with the honest zero.**

    Every URL a2web emits must be traceable to the fetched page. `other_pages`
    is already structurally safe: the model emits `{{n}}` handles and closed-set
    rehydration drops any handle the digest does not know. The hole ADR-0014
    names is the ANSWER PROSE — the model writing a plausible URL from training
    (`python-httpx.org`, `…/reviews`, `…-yorumlari`), which is the closed-set
    guarantee's backdoor and was measured happening live
    (`findings_2026-07-11-answer-inline-links.md`).

    Nine of twelve invariants had zero catching cells and this one still did
    after §6.4: seven criteria across six cases, every one addressed to a judge
    that never receives the page. But it does not NEED a judge. The ADR's own
    wording is a membership test — "a URL literally present in the page
    content" — so the check is: does each URL in the answer appear in the body
    we retrieved, in the index we emitted, or as the page's own address?

    **Known false-positive mode, stated rather than papered over:** an anchor
    whose href never survives extraction into `content_md` would read as
    untraceable. That is a wrong red, and acceptable here in a way it would not
    be in production — a URL in the answer that is absent from the body we
    captured is worth a human look whichever way it resolves. Do not port this
    into the fetch path as a filter.
    """
    if expected is not True:
        return [f"answer_urls_traceable: only `true` is meaningful, got {expected!r}"]

    index = observed.get("index") or {}
    haystack = " ".join(
        [
            str(observed.get("content_md") or ""),
            str(observed.get("page_url") or ""),
            *[str(r.get("url") or "") for r in index.get("other_pages") or ()],
            *[str(r.get("url") or "") for r in index.get("options") or ()],
        ]
    )
    out: list[str] = []
    for raw in _URL_IN_PROSE.findall(str(observed.get("answer") or "")):
        url = raw.rstrip(_URL_TRAILING)
        if url and url not in haystack:
            out.append(
                f"answer_urls_traceable: {url!r} appears in the answer but nowhere in the "
                "fetched page, the emitted index, or the page's own address — ADR-0014: a "
                "URL a2web could not have read is a manufactured hit"
            )
    return out


def _check_index(key: str, expected: Any, observed: Mapping[str, Any]) -> list[str]:
    """The ADR-0015 withheld-body index: `other_pages` / `options` / `also_here`
    / `refinement_axes`.

    **The per-row keys (`other_pages_kinds`, `other_pages_all_have_anchor`,
    `options_all_have_url`) are vacuously true over an EMPTY index.** A case
    that pins one must also pin the matching `*_min`, or an index that vanished
    entirely satisfies it — a guard that reads green because there is nothing
    left to check. Nothing enforces the pairing; it is a rule for whoever
    writes the case, stated here because it is the failure this whole change is
    about.

    Read off a structured projection (`observed["index"]`), never off the wire
    string. `AskResponse` renders `other_pages` and `options` as TSV blocks, and
    a checker that parsed those blocks back into rows would be asserting the
    encoder as much as the index — the thing under test would be sharing a
    failure mode with the thing testing it.
    """
    index = observed.get("index") or {}
    other = list(index.get("other_pages") or ())
    options = list(index.get("options") or ())
    out: list[str] = []

    if key == "other_pages_min":
        if len(other) < expected:
            out.append(f"other_pages_min: {len(other)} < {expected}")
    elif key == "other_pages_kinds":
        allowed = set(expected)
        out.extend(
            f"other_pages_kinds: entry {row.get('anchor') or row.get('url')!r} has kind "
            f"{row.get('kind')!r}, allowed {sorted(allowed)}"
            for row in other
            if row.get("kind") not in allowed
        )
    elif key == "other_pages_all_have_anchor":
        # Only `true` is meaningful — "some rows must LACK an anchor" is not an
        # invariant anyone wants. `false` is rejected rather than treated as a
        # no-op, so a case cannot disarm its own assertion by flipping a bool.
        if expected is not True:
            out.append(f"other_pages_all_have_anchor: only `true` is meaningful, got {expected!r}")
        else:
            missing = [row.get("url") for row in other if not (row.get("anchor") or "").strip()]
            if missing:
                out.append(f"other_pages_all_have_anchor: {len(missing)} row(s) carry no anchor: {missing}")
    elif key == "options_min":
        if len(options) < expected:
            out.append(f"options_min: {len(options)} < {expected}")
    elif key == "options_max":
        if len(options) > expected:
            out.append(f"options_max: {len(options)} > {expected}")
    elif key == "options_all_have_url":
        # `true`-only for the same reason as `other_pages_all_have_anchor`: a
        # `false` branch that asserts nothing is a case's own off switch.
        if expected is not True:
            out.append(f"options_all_have_url: only `true` is meaningful, got {expected!r}")
        else:
            missing = [row.get("title") for row in options if not (row.get("url") or "").strip()]
            if missing:
                out.append(f"options_all_have_url: {len(missing)} option(s) carry no URL: {missing}")
    elif key == "index_non_empty":
        populated = any(
            index.get(name) for name in ("other_pages", "options", "also_here", "refinement_axes")
        )
        if populated is not bool(expected):
            out.append(
                f"index_non_empty: expected {bool(expected)}, but other_pages/options/also_here/"
                f"refinement_axes are {'all empty' if not populated else 'populated'} — "
                "ADR-0015: withholding the body without leaving an index is a silent miss"
            )
    elif key == "also_here_min":
        if len(list(index.get("also_here") or ())) < expected:
            out.append(f"also_here_min: {len(list(index.get('also_here') or ()))} < {expected}")
    else:
        # This branch is the reason the function ends in `else` rather than
        # falling off the end. `check_contract_keys` routes everything it did
        # not handle itself here, so a key added to `CONTRACT_KEYS` and nowhere
        # else would return no failures — a declared assertion that checks
        # nothing, which is precisely this change's subject. Pinned by
        # `test_every_declared_key_is_implemented`.
        out.append(f"contract key {key!r} is declared but has no implementation")
    return out


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


__all__ = ["BENCH_ONLY_KEYS", "CONTRACT_KEYS", "REPLAY_ONLY_KEYS", "check_contract_keys"]
