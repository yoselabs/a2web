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

from typing import TYPE_CHECKING, Any

from a2kit.testing import lazy as lazy_value

from a2web import fetcher
from tests.conftest import make_default_state

from .harness import CassetteBrowserPool, CassetteLlm, patch_fetch_bytes

if TYPE_CHECKING:
    import pytest

    from eval._capture.corpus import ReplayCase


async def replay_case(monkeypatch: pytest.MonkeyPatch, case: ReplayCase) -> dict[str, Any]:
    """Replay one case deterministically and return its observed contract."""
    patch_fetch_bytes(monkeypatch, case)
    state = make_default_state()
    browser_lazy = lazy_value(CassetteBrowserPool(case))
    llm_lazy = lazy_value(CassetteLlm(case))

    response = await fetcher.fetch(
        case.url,
        state=state,
        browser_pool=browser_lazy,
        llm_extractor=llm_lazy,
        ask=case.question,
        next_links=True,
        debug=True,
    )
    return observe(response)


def observe(response: Any) -> dict[str, Any]:
    """Project a `FetchResponse` into the deterministic, replay-stable fields."""
    status = getattr(response.status, "value", response.status)
    return {
        "tier": response.tier,
        "status": status,
        "has_content": bool(response.content_md),
        "content_len": len(response.content_md or ""),
        "answer": response.extracted_answer,
        "answer_present": bool(response.extracted_answer),
        "tokens_full": response.tokens.full if response.tokens else 0,
        "next_links_count": len(response.next_links),
        "operator_hints": sorted(h.code for h in response.operator_hints),
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

    Deterministic axes only — answer *quality* is judged under `make bench`.
    """
    contract = case.baseline.contract
    if not contract:
        raise ContractMismatch(f"case {case.slug!r} has no blessed baseline/contract.json — capture/bless it first")

    failures: list[str] = []
    for key, expected in contract.items():
        if key in {"tier", "status"}:
            if observed.get(key) != expected:
                failures.append(f"{key}: expected {expected!r}, got {observed.get(key)!r}")
        elif key in {"has_content", "answer_present"}:
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
        else:
            failures.append(f"unknown contract key {key!r}")

    if failures:
        ref = f"{case.corpus}/{case.slug}" if case.corpus else case.slug
        raise ContractMismatch(
            f"contract regression for case '{ref}':\n  " + "\n  ".join(failures) + f"\n(re-bless: make eval-refresh CASE={ref})"
        )
