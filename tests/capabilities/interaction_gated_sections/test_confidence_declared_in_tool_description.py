"""The `query` tool description declares what `confidence` grades and that
`operator_hints[].code` is the branching surface — closing the gap that let
`low` be misread as "distrust the answer, retry" (ADR-0020 design notes)."""

from __future__ import annotations

import pytest

from a2web.components import build_components
from tests._helpers.mcp import mcp_client


@pytest.mark.asyncio
async def test_query_tool_description_declares_confidence_and_hint_branching() -> None:
    parts = build_components()
    async with mcp_client(components=parts) as client:
        tools = {t.name: t for t in await client.list_tools()}
    description = tools["query"].description or ""
    assert "confidence" in description.lower()
    assert "retrieval" in description.lower()
    assert "operator_hints[].code" in description
