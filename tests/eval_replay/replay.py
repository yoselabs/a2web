"""Replay driver + contract assertions.

`replay_case` runs the real `fetcher.fetch` orchestrator over a frozen
case: the raw/jina/archive egress is served by the patched `fetch_bytes`,
the browser and LLM egresses by `Lazy`-wrapped cassette resources at the
tool seam. Nothing above the egress is stubbed — gate, ladder, and
escalation logic run for real. `observe` projects the produced
`FetchResponse` into a deterministic dict; `assert_contract` checks that
dict against the case's blessed `baseline/contract.json`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from a2web import fetcher
from a2web.lazy import lazy as lazy_value
from tests.conftest import make_default_state

from .harness import CassetteBrowserPool, CassetteLlm, patch_fetch_bytes

if TYPE_CHECKING:
    import pytest

    from eval._capture.corpus import ReplayCase


async def replay_case(monkeypatch: pytest.MonkeyPatch, case: ReplayCase) -> dict[str, Any]:
    """Replay one case deterministically and return its observed contract."""
    patch_fetch_bytes(monkeypatch, case)
    state = make_default_state()
    cassette_llm = CassetteLlm(case)
    browser_lazy = lazy_value(CassetteBrowserPool(case))
    # Both browser rungs (fast + robust) replay from the same frozen DOM — the
    # cassette is engine-agnostic, so fast→robust escalation serves identical
    # bytes and the contract is unchanged by the rung that produced them.
    browser_robust_lazy = lazy_value(CassetteBrowserPool(case))
    llm_lazy = lazy_value(cassette_llm)

    response = await fetcher.fetch(
        case.url,
        state=state,
        browser_backend=browser_lazy,
        browser_robust_backend=browser_robust_lazy,
        llm_extractor=llm_lazy,
        ask=case.question,
        next_links=True,
        debug=True,
    )
    return observe(response, input_menu=cassette_llm.last_extract_content)


_FETCHED_AT_RE = re.compile(r"fetched_at=[0-9T:+\-Z]+")
#: Every `fmt_dur` output shape — `8ms`, `1.2s`, `12s`, `1m03s`. The narrative
#: is built from real wall-clock timings ("raw → ok (8ms)."), so it is the one
#: field in this projection that is NOT deterministic from frozen bytes. Caught
#: by `test_selftest_replay_is_reproducible` the moment `narrative` was added,
#: which is exactly what that test is for: a projection field that drifts by a
#: millisecond would make every replay baseline flap and the corpus would be
#: re-blessed into meaninglessness within a week.
_DURATION_RE = re.compile(r"\b\d+m\d{2}s\b|\b\d+\.\d+s\b|\b\d+m?s\b")


def observe(response: Any, *, input_menu: str | None = None) -> dict[str, Any]:
    """Project a `FetchResponse` into the deterministic, replay-stable fields.

    `input_menu` is the exact content string the extractor (Haiku) was fed —
    captured by the cassette spy. The fidelity gate asserts against this (the
    menu), independent of the wire `content_md` (ADR-0005 D7).
    """
    status = getattr(response.status, "value", response.status)
    # The content wrapper embeds a wall-clock `fetched_at=`; scrub it so the
    # projection is byte-stable across replays (the body itself is deterministic
    # from frozen bytes).
    content_md = _FETCHED_AT_RE.sub("fetched_at=<scrubbed>", response.content_md or "")
    menu = _FETCHED_AT_RE.sub("fetched_at=<scrubbed>", input_menu) if input_menu else ""
    narrative = _DURATION_RE.sub("<dur>", response.narrative or "")
    return {
        "tier": response.tier,
        "status": status,
        "has_content": bool(response.content_md),
        "content_len": len(response.content_md or ""),
        "content_md": content_md,
        "input_menu": menu,
        "answer": response.extracted_answer,
        "answer_present": bool(response.extracted_answer),
        "tokens_full": response.tokens.full if response.tokens else 0,
        "next_links_count": len(response.next_links),
        "operator_hints": sorted(h.code for h in response.operator_hints),
        # ADR-0009's two prose-independent failure signals. Absent from this
        # projection until 2026-08-02, which meant the akakce wall baseline —
        # the corpus's canonical "a2web was stopped and said so" case — could
        # not regress on either. A wall that quietly stopped setting
        # `retrieval_incomplete`, or stopped explaining itself, replayed green:
        # `status: failed` + the `try_user_browser` hint were the only things
        # asserted, and neither is the flag a caller branches on.
        #
        # `narrative` is captured as a PRESENCE bool plus the text, not as an
        # exact match. It is tuned operator prose; asserting it byte-for-byte
        # would make every wording pass a baseline re-bless, which is how a
        # golden stops meaning anything. Cases that care about specific wording
        # use the `narrative_includes` intent key.
        # THE PLANNER'S FOREIGN WITNESS (§4.1). The ordered `(step, verdict)`
        # pairs a fetch actually dispatched — the RESULT of every routing
        # decision `actions/playbook.py` made, observed rather than restated.
        #
        # Why this and not more table tests: 49 of the 53 cases in
        # `test_decide_next.py` assert the rule table by re-encoding the same
        # table in the test, so a wrong rule and its test agree and both stay
        # green. This projection is produced by a different mechanism entirely
        # — the real orchestrator over frozen bytes — so it cannot agree with
        # the planner by construction. If a rule stops firing, or fires where
        # it did not, the dispatch sequence changes and the blessed baseline
        # fails, with nothing in the corpus mentioning a rule name.
        #
        # Deterministic: both fields derive from frozen bytes. Durations are
        # deliberately NOT included for the reason `_DURATION_RE` exists.
        "steps": [f"{d.step}:{getattr(d.verdict, 'value', d.verdict)}" for d in response.diagnostics],
        "retrieval_incomplete": bool(response.retrieval_incomplete),
        "narrative": narrative,
        "narrative_present": bool((response.narrative or "").strip()),
    }


class ContractMismatch(AssertionError):
    """A replayed case violated its blessed contract."""


def assert_contract(case: ReplayCase, observed: dict[str, Any]) -> None:
    """Compare `observed` against the case's blessed `baseline/contract.json`.

    Supported assertion keys (only those present are checked):

      tier, status               exact match
      has_content, answer_present  bool match
      answer_contains            substring of `answer`
      tokens_full_max            observed tokens_full <= value
      next_links_min             observed next_links_count >= value
      operator_hints             exact sorted list
      steps                      exact ordered `tier:verdict` dispatch sequence
      retrieval_incomplete       bool match — ADR-0009's caller-facing flag
      narrative_present          bool match — a failure must explain itself
      narrative_includes         every listed substring IS in `narrative`
      content_includes           every listed substring IS in content_md
      content_excludes           no listed substring is in content_md
      input_menu_includes        every listed substring IS in the extractor menu
      input_menu_excludes        no listed substring is in the extractor menu

    Deterministic axes only — answer *quality* is judged under `make bench`.
    `content_includes` / `content_excludes` assert the wire projection itself
    (from frozen bytes, no LLM). `input_menu_includes` / `input_menu_excludes`
    assert what the extractor (Haiku) was actually fed — the offline gate for
    the multi-source-menu fix (ADR-0005 D7), independent of the wire.
    """
    contract = case.baseline.contract
    if not contract:
        raise ContractMismatch(f"case {case.slug!r} has no blessed baseline/contract.json — capture/bless it first")

    failures: list[str] = []
    for key, expected in contract.items():
        if key in {"tier", "status"}:
            if observed.get(key) != expected:
                failures.append(f"{key}: expected {expected!r}, got {observed.get(key)!r}")
        elif key in {"has_content", "answer_present", "retrieval_incomplete", "narrative_present"}:
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
        elif key == "content_includes":
            content = observed.get("content_md") or ""
            for needle in expected:
                if str(needle) not in content:
                    failures.append(f"content_includes: {needle!r} not in projected content")
        elif key == "content_excludes":
            content = observed.get("content_md") or ""
            for needle in expected:
                if str(needle) in content:
                    failures.append(f"content_excludes: fused/forbidden token {needle!r} present in projected content")
        elif key == "input_menu_includes":
            menu = observed.get("input_menu") or ""
            for needle in expected:
                if str(needle) not in menu:
                    failures.append(f"input_menu_includes: {needle!r} not in the content fed to the extractor")
        elif key == "narrative_includes":
            narrative = observed.get("narrative") or ""
            for needle in expected:
                if str(needle) not in narrative:
                    failures.append(f"narrative_includes: {needle!r} not in narrative {narrative[:160]!r}")
        elif key == "input_menu_excludes":
            menu = observed.get("input_menu") or ""
            for needle in expected:
                if str(needle) in menu:
                    failures.append(f"input_menu_excludes: forbidden token {needle!r} present in extractor input")
        else:
            failures.append(f"unknown contract key {key!r}")

    if failures:
        ref = f"{case.corpus}/{case.slug}" if case.corpus else case.slug
        raise ContractMismatch(
            f"contract regression for case '{ref}':\n  " + "\n  ".join(failures) + f"\n(re-bless: make eval-refresh CASE={ref})"
        )
