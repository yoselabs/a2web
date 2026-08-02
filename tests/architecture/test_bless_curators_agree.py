"""The two contract curators produce the same key set.

There are two paths that write a case's `baseline/contract.json`:

  `tests/eval_replay/bless.py::curate_contract`   — replay bless, from `observed`
  `eval/_capture/capture.py::_curate_contract`    — live capture / `make eval-refresh`

They disagreed until 2026-08-02, and the disagreement was invisible in the worst
possible way. The replay curator blessed `steps` unconditionally,
`retrieval_incomplete` / `narrative_present` on a non-ok status, and carried
hand-authored intent keys forward — each with a comment explaining that a
truthy-gated key would vanish from the baseline exactly when it stopped holding.
The capture curator did none of it, and `make eval-refresh` — the command the
mismatch message tells an operator to run — uses THAT one.

So the documented way to re-bless silently deleted assertions. It is why two of
eight regression baselines carried no `steps` while the change that introduced
them recorded the work as done: the bless code was correct, but only one of the
two bless codes, and the other was the one people ran.

This guard compares the KEY SETS both produce for the same synthetic response.
It deliberately does not compare values — the two curators read different
inputs (a projection dict vs a live `FetchResponse`), so identical values are
not the contract. Identical *assertions* are.
"""

from __future__ import annotations

from typing import Any

from eval._capture.capture import _curate_contract
from tests.eval_replay.bless import curate_contract


class _Diag:
    def __init__(self, step: str, verdict: str) -> None:
        self.step = step
        self.verdict = verdict


class _Tokens:
    full = 1200


class _Response:
    """The minimum surface `_curate_contract` reads off a `FetchResponse`."""

    def __init__(self, *, status: str, hints: tuple[str, ...] = ()) -> None:
        self.tier = "raw"
        self.status = status
        self.content_md = "body text"
        self.extracted_answer = "an answer"
        self.tokens = _Tokens()
        self.next_links = ()
        self.operator_hints = tuple(type("H", (), {"code": c})() for c in hints)
        self.diagnostics = (_Diag("raw", "ok"), _Diag("gate", "ok"))
        self.retrieval_incomplete = status != "ok"
        self.narrative = "why it failed" if status != "ok" else None


def _observed(*, status: str, hints: tuple[str, ...] = ()) -> dict[str, Any]:
    """The replay-side projection describing the SAME run as `_Response`."""
    return {
        "tier": "raw",
        "status": status,
        "has_content": True,
        "answer_present": True,
        "tokens_full": 1200,
        "next_links_count": 0,
        "operator_hints": list(hints),
        "steps": ["raw:ok", "gate:ok"],
        "retrieval_incomplete": status != "ok",
        "narrative_present": status != "ok",
    }


def test_ok_status_curates_the_same_keys() -> None:
    assert set(curate_contract(_observed(status="ok"))) == set(_curate_contract(_Response(status="ok")))


def test_failed_status_curates_the_same_keys() -> None:
    """The case that mattered — ADR-0009's completeness keys are failure-only."""
    replay = curate_contract(_observed(status="failed", hints=("try_user_browser",)))
    capture = _curate_contract(_Response(status="failed", hints=("try_user_browser",)))

    assert set(replay) == set(capture)
    # Non-vacuity: the failure-only keys must actually be present, or this test
    # would pass just as happily over two curators that both emit nothing.
    assert {"retrieval_incomplete", "narrative_present", "steps"} <= set(replay)


def test_both_carry_hand_authored_intent_keys_forward() -> None:
    """A re-bless must never drop a case's acceptance gate.

    The capture curator had no notion of these at all, so `make eval-refresh`
    deleted every `content_includes` / `answer_contains` it met.
    """
    prior = {"content_includes": ["Fiyat Yok"], "answer_contains": ["no price"]}

    capture = _curate_contract(_Response(status="ok"), prior=prior)

    assert capture["content_includes"] == ["Fiyat Yok"]
    assert capture["answer_contains"] == ["no price"]


def test_steps_survives_an_empty_dispatch() -> None:
    """`steps` is blessed unconditionally, not when truthy.

    A truthy gate would delete the key exactly when the sequence went empty —
    losing the assertion at the moment it started failing.
    """
    response = _Response(status="ok")
    response.diagnostics = ()

    assert "steps" in _curate_contract(response)
    assert _curate_contract(response)["steps"] == []
