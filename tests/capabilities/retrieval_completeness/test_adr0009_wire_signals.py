"""All five ADR-0009 signals reach the wire on a walled fetch — plus severity.

The invariant: *a walled/failed fetch MUST carry `status: failed` +
`retrieval_incomplete: true` + populated `diagnostics` + `narrative` + a
critical `try_user_browser` operator hint.* Five signals, and the caller must
never be able to mistake a miss for a complete answer.

Until 2026-08-01 that invariant was checked by three `assert`s sitting inline in
`test_wire_query_failure`, a GOLDEN test. Two problems with that:

1. It covered three of the five. `narrative` and `diagnostics` were carried only
   by the golden file, which pins the bytes without asserting their meaning —
   an accepted re-bless with a reason would take them away silently.
2. **`severity` was checked by nothing.** The hint's presence was asserted by
   substring; its `critical` marking was not. That is exactly the field the TSV
   column-union bug (2026-07-31) stripped from the agent's view while
   `structured_content` stayed correct.

So the signals live here, in a standalone capability test that no golden
re-bless can weaken, and `test_wire_query_failure` keeps its byte-level job.
"""

from __future__ import annotations

import pytest

from tests.contracts.test_wire_contract import _query_wire, _text
from tests.fixtures import FIXTURES_DIR


@pytest.mark.asyncio
async def test_all_five_adr0009_signals_are_present(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "cloudflare_block.html").read_bytes(),
        url="https://blocked.example/page",
        query="q",
    )
    sc = payload["structured_content"]

    assert payload["is_error"] is False, "a wall is data, not a transport error"
    assert sc["status"] == "failed"
    assert sc["retrieval_incomplete"] is True
    # `diagnostics_summary`, not `diagnostics`. The invariant is usually written
    # as "populated `diagnostics`", but the full list is DEBUG-GATED — the
    # serializer regroups it under `debug` and it is absent from a default
    # response. What a normal caller actually receives on a wall is the
    # failure-only summary; asserting the debug field here would have been
    # asserting something the default wire never carries.
    assert sc.get("diagnostics_summary"), "the failure-only diagnostics summary must be populated"
    assert "verdict=" in sc["diagnostics_summary"], "the summary must name what actually happened"
    assert sc.get("narrative"), "the caller needs the prose story of what was tried"

    hints = sc.get("operator_hints") or []
    wall = next((h for h in hints if h.get("code") == "try_user_browser"), None)
    assert wall is not None, f"the ADR-0009 klaxon is missing (hints: {[h.get('code') for h in hints]})"


@pytest.mark.asyncio
async def test_the_full_diagnostics_list_arrives_under_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of the field-tier split, so the omission above is deliberate.

    Without this, the assertion on `diagnostics_summary` reads as though the
    full list simply does not exist. It does — it is debug-gated, which is the
    designed tiering, not a gap.
    """
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "cloudflare_block.html").read_bytes(),
        url="https://blocked.example/page",
        query="q",
        debug=True,
    )
    sc = payload["structured_content"]
    debug = sc.get("debug") or {}
    assert debug.get("diagnostics"), f"debug=True must carry the full diagnostics list (keys: {sorted(debug)})"


@pytest.mark.asyncio
async def test_the_wall_hint_reaches_the_agent_marked_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    """The severity, asserted on the AGENT's channel — the one that was wrong.

    `structured_content` carried `critical` correctly all along; the TSV table in
    `content[0].text` dropped the column whenever a quieter hint came first,
    because the header was derived from `rows[0]`. ADR-0009's loudest signal
    reached the model unmarked, and ~1350 field-presence assertions could not see
    it because they all read the machine channel.

    So this reads `content[0].text` deliberately. When the agent's view is the
    point, assert on the agent's view.
    """
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "cloudflare_block.html").read_bytes(),
        url="https://blocked.example/page",
        query="q",
    )

    hints = payload["structured_content"].get("operator_hints") or []
    wall = next(h for h in hints if h.get("code") == "try_user_browser")
    assert wall.get("severity") == "critical", f"the wall hint is marked {wall.get('severity')!r}"

    text = _text(payload)
    assert "try_user_browser" in text
    assert "critical" in text, "the severity did not survive into the agent-facing channel"
