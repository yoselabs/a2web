"""Breaking corpus — cases deliberately spanning failure classes A/B/C.

Deterministic replay over frozen cassettes; gates `make check`. Same shape as
the regression corpus: asserts each case's blessed `baseline/contract.json`
(tier / status / content / token bound / `answer_contains`), NOT live answer
quality (that is the `make bench` judged axis).

Class coverage across the substrate:
  - A (clean structured schema): `arxiv-attention-clean-schema` (abstract via the
    arxiv handler), `allrecipes-nutrition` (clean Recipe JSON-LD — also confirms
    the change-#4 recipe rendering generalizes off bbcgoodfood).
  - B (source omits the asked fact → honest "not present", no fabrication):
    `wikipedia-absent-fact`.
  - C ("structured data present but wrong/misleading") is exemplified by the
    `regression` corpus (`hepsiburada-listing-price` price-fusion,
    `recipe-nutrition-volume-gate` sidebar mis-selection) — real stuck-cases the
    extraction-fidelity program produced. A fresh non-Cloudflare-walled C is
    impractical to capture (misleading-schema retailers sit behind CF), so the
    substrate's C coverage lives there rather than being duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval._capture.corpus import load_corpus
from tests.eval_replay.bless import BLESS_EVAL, bless_contract
from tests.eval_replay.replay import assert_contract, replay_case

_BREAKING = Path(__file__).resolve().parents[2] / "eval" / "corpus" / "breaking"
_CASES = load_corpus(_BREAKING)


@pytest.mark.skipif(not _CASES, reason="no breaking cases captured yet")
@pytest.mark.parametrize("case", _CASES, ids=[c.slug for c in _CASES])
async def test_breaking_replay(monkeypatch: pytest.MonkeyPatch, case) -> None:
    observed = await replay_case(monkeypatch, case)
    if BLESS_EVAL:
        bless_contract(case, observed)
        return
    assert_contract(case, observed)
