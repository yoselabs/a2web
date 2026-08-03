"""The per-case contract vocabulary is ONE implementation with two consumers.

`tests/eval_replay/` asserts it offline against frozen bytes; `make bench`
asserts it live. The point of these tests is the seam, not the individual
comparisons: a key must mean the same thing in both, and a key the live bench
cannot observe must be reported as unobservable rather than passing.
"""

from __future__ import annotations

import pytest

from a2web.llm_eval.case_contract import (
    BENCH_ONLY_KEYS,
    CONTRACT_KEYS,
    REPLAY_ONLY_KEYS,
    check_contract_keys,
)
from a2web.llm_eval.runner import _observe_for_contract
from a2web.llm_eval.systems import SystemResult

_OK = {
    "tier": "raw",
    "status": "ok",
    "has_content": True,
    "content_md": "hello world",
    "answer": "the answer",
    "answer_present": True,
    "narrative": "raw → ok",
    "narrative_present": True,
    "retrieval_incomplete": False,
    "tokens_full": 100,
    "next_links_count": 3,
    "operator_hints": ["cookies_stale"],
    "hint_severities": {"cookies_stale": "info"},
    "confidence": "medium",
    "index": {
        "other_pages": [
            {"kind": "drilldown", "url": "https://x/a", "anchor": "Item A"},
            {"kind": "drilldown", "url": "https://x/b", "anchor": "Item B"},
        ],
        "options": [{"title": "A", "url": "https://x/a", "detail": "₺10"}],
        "also_here": ["shipping terms"],
        "refinement_axes": [],
    },
}


def test_a_satisfied_contract_produces_no_failures() -> None:
    failures, unsupported = check_contract_keys({"status": "ok", "tier": "raw", "answer_present": True, "next_links_min": 2}, _OK)
    assert failures == []
    assert unsupported == []


@pytest.mark.parametrize(
    ("contract", "needle"),
    [
        ({"status": "failed"}, "status"),
        ({"tier": "browser"}, "tier"),
        ({"answer_present": False}, "answer_present"),
        ({"next_links_min": 9}, "next_links_min"),
        ({"tokens_full_max": 10}, "tokens_full_max"),
        ({"operator_hints": ["try_user_browser"]}, "operator_hints"),
        ({"answer_contains": "absent"}, "answer_contains"),
        ({"content_includes": ["absent"]}, "content_includes"),
        ({"content_excludes": ["hello"]}, "content_excludes"),
        ({"narrative_includes": ["absent"]}, "narrative_includes"),
        ({"retrieval_incomplete": True}, "retrieval_incomplete"),
        ({"answer_excludes": ["the answer"]}, "answer_excludes"),
        ({"operator_hints_include": ["try_user_browser"]}, "operator_hints_include"),
        ({"operator_hints_exclude": ["cookies_stale"]}, "operator_hints_exclude"),
        ({"hint_severity": {"cookies_stale": "critical"}}, "hint_severity"),
        ({"hint_severity": {"try_user_browser": "critical"}}, "hint_severity"),
        ({"confidence_max": "low"}, "confidence_max"),
        ({"other_pages_min": 5}, "other_pages_min"),
        ({"other_pages_kinds": ["structural"]}, "other_pages_kinds"),
        ({"options_min": 3}, "options_min"),
        ({"options_max": 0}, "options_max"),
        ({"also_here_min": 4}, "also_here_min"),
        ({"index_non_empty": False}, "index_non_empty"),
    ],
)
def test_every_key_can_actually_fail(contract: dict, needle: str) -> None:
    """Each key is exercised against an observation that violates it.

    A vocabulary whose keys are only ever tested in their passing direction is
    the guard-that-reads-green shape: a key wired to nothing looks identical to
    a key that agrees.
    """
    failures, _ = check_contract_keys(contract, _OK)
    assert failures, f"{needle} accepted a violating observation"
    assert needle in failures[0]


def test_a_satisfied_index_contract_produces_no_failures() -> None:
    """The passing direction for the whole ADR-0015 index group, so the failing
    parametrization above is read against a known-good baseline."""
    failures, unsupported = check_contract_keys(
        {
            "other_pages_min": 2,
            "other_pages_kinds": ["drilldown", "structural"],
            "other_pages_all_have_anchor": True,
            "options_min": 1,
            "options_max": 2,
            "options_all_have_url": True,
            "also_here_min": 1,
            "index_non_empty": True,
            "confidence_max": "high",
            "hint_severity": {"cookies_stale": "info"},
            "operator_hints_include": ["cookies_stale"],
            "operator_hints_exclude": ["try_user_browser"],
            "answer_excludes": ["```"],
        },
        _OK,
    )
    assert failures == []
    assert unsupported == []


def test_an_anchorless_other_page_fails() -> None:
    observed = dict(_OK)
    observed["index"] = dict(_OK["index"], other_pages=[{"kind": "drilldown", "url": "https://x/a"}])
    failures, _ = check_contract_keys({"other_pages_all_have_anchor": True}, observed)
    assert failures and "carry no anchor" in failures[0]


def test_other_pages_all_have_anchor_rejects_false_rather_than_no_opping() -> None:
    """A bool key whose `false` branch asserts nothing is a case's own off
    switch. Reject it instead."""
    failures, _ = check_contract_keys({"other_pages_all_have_anchor": False}, _OK)
    assert failures and "only `true` is meaningful" in failures[0]


def test_a_urlless_option_fails() -> None:
    """Page chrome surfaced as a selectable option carries no URL — the defect
    `hepsiburada-product-no-footer-options` exists to catch."""
    observed = dict(_OK)
    observed["index"] = dict(_OK["index"], options=[{"title": "Kurumsal", "url": None}])
    failures, _ = check_contract_keys({"options_all_have_url": True}, observed)
    assert failures and "carry no URL" in failures[0]


def test_hint_severity_fails_when_the_hint_never_fired() -> None:
    """Distinct from a severity mismatch: 'the klaxon is quiet' and 'the klaxon
    never sounded' are different regressions and must read differently."""
    failures, _ = check_contract_keys({"hint_severity": {"try_user_browser": "critical"}}, _OK)
    assert failures and "did not fire at all" in failures[0]


def test_confidence_max_is_a_ceiling_not_an_equality() -> None:
    """`medium` observed under a `high` ceiling passes — the key exists to stop
    an envelope OVER-claiming, not to pin a value."""
    failures, _ = check_contract_keys({"confidence_max": "high"}, _OK)
    assert failures == []


def test_every_declared_key_is_implemented() -> None:
    """Non-vacuity for the vocabulary itself.

    `check_contract_keys` routes anything it does not handle inline to
    `_check_index`, so a key added to `CONTRACT_KEYS` and nowhere else would
    return no failures — a declared assertion that checks nothing, which is the
    whole subject of this change. Every key is driven here with a value that
    must fail against an empty observation.
    """
    for key in sorted(CONTRACT_KEYS - REPLAY_ONLY_KEYS):
        probe = _IMPOSSIBLE[key]
        observed = _IMPOSSIBLE_AGAINST.get(key, {})
        failures, unsupported = check_contract_keys({key: probe}, observed)
        assert not unsupported, key
        assert failures, f"{key} produced no failure against {observed!r} — it is unimplemented"
        assert "no implementation" not in failures[0], failures[0]


#: For each key, a value that CANNOT be satisfied by the observation it is
#: driven against. Literal per key rather than derived: a generated probe would
#: be as likely to be vacuous as the thing it is checking.
_IMPOSSIBLE: dict = {
    "tier": "browser",
    "status": "failed",
    "has_content": True,
    "answer_present": True,
    "retrieval_incomplete": True,
    "narrative_present": True,
    "answer_contains": "nope",
    "tokens_full_max": -1,
    "next_links_min": 1,
    "operator_hints": ["x"],
    "content_includes": ["nope"],
    "content_excludes": [""],
    "narrative_includes": ["nope"],
    "answer_excludes": [""],
    "operator_hints_include": ["x"],
    "operator_hints_exclude": [""],
    "hint_severity": {"x": "critical"},
    "confidence_max": "high",
    "other_pages_min": 1,
    "other_pages_kinds": [],
    "other_pages_all_have_anchor": False,
    "options_min": 1,
    "options_max": -1,
    "options_all_have_url": False,
    "also_here_min": 1,
    "index_non_empty": True,
    "answer_urls_traceable": False,
}

#: Keys an EMPTY observation cannot falsify, with an observation that can. An
#: exclusion key is satisfied by absence by construction, so driving it against
#: nothing would prove only that nothing is absent.
_IMPOSSIBLE_AGAINST: dict = {
    "operator_hints_exclude": {"operator_hints": [""]},
    # A per-row predicate is vacuously true over zero rows. That is a real
    # property of the key, not a gap: a case pinning `other_pages_kinds` must
    # ALSO pin `other_pages_min`, or an index that vanished entirely would
    # satisfy it. Said in the vocabulary's docstring too.
    "other_pages_kinds": {"index": {"other_pages": [{"kind": "structural", "url": "u"}]}},
}


def test_bench_only_keys_are_unsupported_offline() -> None:
    """The mirror of the replay-only split: the offline harness drives
    `fetch_raw`'s `FetchResponse`, which has no ADR-0015 index at all."""
    assert BENCH_ONLY_KEYS
    assert BENCH_ONLY_KEYS < CONTRACT_KEYS
    assert not (BENCH_ONLY_KEYS & REPLAY_ONLY_KEYS)
    failures, unsupported = check_contract_keys({"other_pages_min": 99, "status": "ok"}, _OK, supported=CONTRACT_KEYS - BENCH_ONLY_KEYS)
    assert unsupported == ["other_pages_min"]
    assert failures == []


def test_an_unknown_key_is_a_failure_not_a_skip() -> None:
    """A typo must break the case, not silently assert nothing."""
    failures, _ = check_contract_keys({"stauts": "ok"}, _OK)
    assert failures == ["unknown contract key 'stauts'"]


def test_replay_only_keys_are_reported_unsupported_not_passed() -> None:
    """The live bench has no cassette spy. `steps` must come back as
    unobservable — the one outcome that is neither a pass nor a failure."""
    supported = CONTRACT_KEYS - REPLAY_ONLY_KEYS
    failures, unsupported = check_contract_keys({"steps": ["raw:ok"], "status": "ok"}, _OK, supported=supported)
    assert unsupported == ["steps"]
    assert failures == []


def test_the_replay_only_set_is_real_and_bounded() -> None:
    """Non-vacuity: the split must be a real partition of a real vocabulary."""
    assert REPLAY_ONLY_KEYS
    assert REPLAY_ONLY_KEYS < CONTRACT_KEYS
    assert len(CONTRACT_KEYS) > len(REPLAY_ONLY_KEYS) + 5


def test_live_projection_supplies_the_deviation_only_defaults() -> None:
    """`tier` and `status` are deviation-only on the wire — absent means the
    boring default. A projection that reported `None` would fail every case
    pinning the common path, so the default is re-supplied here."""
    result = SystemResult(answer="a", system="a2web_extract", latency_ms=1, metadata={"envelope": {"answer": "a"}})
    observed = _observe_for_contract(result)
    assert observed["tier"] == "raw"
    assert observed["status"] == "ok"


def test_live_projection_uses_the_same_key_names_as_replay() -> None:
    """The identity that makes one `contract:` block mean the same thing in
    both harnesses. If a projection renames a key, its assertions silently stop
    running — this is the test that notices."""
    from tests.eval_replay import replay

    result = SystemResult(
        answer="a",
        system="a2web_extract",
        latency_ms=1,
        metadata={"envelope": {"answer": "a", "status": "failed", "operator_hints": []}},
    )
    live = set(_observe_for_contract(result))
    offline = set(replay.observe(_FakeResponse()))
    shared = live & offline
    # Each side may project fields the other cannot — but ONLY the declared
    # ones. An undeclared divergence is a rename, and a renamed key stops its
    # assertions running without failing anything.
    assert live - offline == _BENCH_ONLY_PROJECTION, f"live projection invented key(s) {sorted(live - offline - _BENCH_ONLY_PROJECTION)}"
    assert len(shared) >= 10


#: The projection fields that back `BENCH_ONLY_KEYS`. Named here so the identity
#: test above can be exact rather than a subset check — a subset check would
#: have absorbed a rename silently, which is the failure it exists to catch.
_BENCH_ONLY_PROJECTION = {"hint_severities", "confidence", "index"}


def test_answer_urls_traceable_accepts_a_url_from_the_page() -> None:
    observed = dict(_OK, answer="See https://x/a for details.", content_md="body [A](https://x/a)")
    failures, _ = check_contract_keys({"answer_urls_traceable": True}, observed)
    assert failures == []


def test_answer_urls_traceable_catches_a_memory_url() -> None:
    """ADR-0014's measured failure: the model writes a plausible URL from
    training into the answer prose, around the closed-set handle guarantee."""
    observed = dict(_OK, answer="Docs are at https://python-httpx.org.", content_md="body [A](https://x/a)")
    failures, _ = check_contract_keys({"answer_urls_traceable": True}, observed)
    assert failures and "python-httpx.org" in failures[0]
    assert "python-httpx.org." not in failures[0], "sentence punctuation leaked into the URL"


def test_answer_urls_traceable_allows_the_pages_own_address() -> None:
    observed = dict(_OK, answer="This page is https://x/here", content_md="", page_url="https://x/here")
    failures, _ = check_contract_keys({"answer_urls_traceable": True}, observed)
    assert failures == []


def test_answer_urls_traceable_allows_a_url_the_index_emitted() -> None:
    """`other_pages` is closed-set rehydrated, so a URL it carries is already
    page-grounded — citing it in the prose is not a fabrication."""
    observed = dict(_OK, answer="Try https://x/b", content_md="", page_url="")
    failures, _ = check_contract_keys({"answer_urls_traceable": True}, observed)
    assert failures == []


def test_answer_with_no_urls_is_vacuously_traceable_and_that_is_known() -> None:
    """Stated as a property, not discovered later: an answer citing nothing
    passes. Pair the key with a case whose answer is EXPECTED to carry links."""
    observed = dict(_OK, answer="No links here at all.", content_md="")
    failures, _ = check_contract_keys({"answer_urls_traceable": True}, observed)
    assert failures == []


class _FakeResponse:
    """Minimal `FetchResponse` stand-in — `replay.observe` reads attributes, and
    building a real one here would couple this seam test to the response model."""

    status = "ok"
    tier = "raw"
    content_md = "x"
    extracted_answer = "a"
    tokens = None
    next_links: list = []  # noqa: RUF012
    diagnostics: list = []  # noqa: RUF012
    operator_hints: list = []  # noqa: RUF012
    narrative = "raw → ok"
    retrieval_incomplete = False
    url = "https://x/here"


# --------------------------------------------------------------------- #
# The shipped corpus, checked offline
# --------------------------------------------------------------------- #


def test_every_shipped_contract_key_is_in_the_vocabulary() -> None:
    """A typo in `eval/corpus.yaml` fails the cell — but only during a live
    run, which costs network and LLM quota. Catch it here for free.

    Without this, the loop is: write `stauts: ok`, spend $10, read a violation
    that says the key is unknown. The bench should be where a case is measured,
    not where it is spellchecked.
    """
    from pathlib import Path

    from a2web.llm_eval.corpus import load_corpus

    supported = CONTRACT_KEYS - REPLAY_ONLY_KEYS
    checked = 0
    for entry in load_corpus(Path("eval/corpus.yaml")).entries:
        contract = entry.extra.get("contract")
        if not contract:
            continue
        checked += 1
        assert isinstance(contract, dict), f"{entry.slug}: `contract:` must be a mapping"
        unknown = sorted(set(contract) - supported)
        assert not unknown, f"{entry.slug}: contract key(s) {unknown} are not in the vocabulary"
    # Non-vacuity: this walk found contracts, not an empty corpus.
    assert checked >= 10, f"only {checked} corpus entries carry a contract — did the loader change?"


def test_shipped_per_row_keys_are_paired_with_a_floor() -> None:
    """The vacuity rule the vocabulary's docstring states, enforced on the
    corpus rather than left to whoever writes the next case.

    `other_pages_kinds: [drilldown]` is satisfied by an index that vanished
    entirely — zero rows, zero violations. Pinning it without
    `other_pages_min` is a guard that reads green precisely when ADR-0015's
    index went missing.
    """
    from pathlib import Path

    from a2web.llm_eval.corpus import load_corpus

    pairing = {
        "other_pages_kinds": "other_pages_min",
        "other_pages_all_have_anchor": "other_pages_min",
        "options_all_have_url": "options_min",
    }
    for entry in load_corpus(Path("eval/corpus.yaml")).entries:
        contract = entry.extra.get("contract") or {}
        for per_row, floor in pairing.items():
            if per_row in contract:
                assert floor in contract, f"{entry.slug}: `{per_row}` is vacuously true over an empty index — pair it with `{floor}`"
