"""The per-case contract vocabulary is ONE implementation with two consumers.

`tests/eval_replay/` asserts it offline against frozen bytes; `make bench`
asserts it live. The point of these tests is the seam, not the individual
comparisons: a key must mean the same thing in both, and a key the live bench
cannot observe must be reported as unobservable rather than passing.
"""

from __future__ import annotations

import pytest

from a2web.llm_eval.case_contract import CONTRACT_KEYS, REPLAY_ONLY_KEYS, check_contract_keys
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
}


def test_a_satisfied_contract_produces_no_failures() -> None:
    failures, unsupported = check_contract_keys(
        {"status": "ok", "tier": "raw", "answer_present": True, "next_links_min": 2}, _OK
    )
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


def test_an_unknown_key_is_a_failure_not_a_skip() -> None:
    """A typo must break the case, not silently assert nothing."""
    failures, _ = check_contract_keys({"stauts": "ok"}, _OK)
    assert failures == ["unknown contract key 'stauts'"]


def test_replay_only_keys_are_reported_unsupported_not_passed() -> None:
    """The live bench has no cassette spy. `steps` must come back as
    unobservable — the one outcome that is neither a pass nor a failure."""
    supported = CONTRACT_KEYS - REPLAY_ONLY_KEYS
    failures, unsupported = check_contract_keys(
        {"steps": ["raw:ok"], "status": "ok"}, _OK, supported=supported
    )
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
    result = SystemResult(
        answer="a", system="a2web_extract", latency_ms=1, metadata={"envelope": {"answer": "a"}}
    )
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
    # Everything the live side projects must be a name the offline side also
    # uses; the offline side is allowed extras (the spy-only fields).
    assert live <= offline, f"live projection invented key(s) {sorted(live - offline)}"
    assert len(shared) >= 10


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
