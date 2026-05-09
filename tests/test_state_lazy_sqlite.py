"""Lazy sqlite singleton + test bootstrap helper tests."""

from __future__ import annotations

import asyncio

import pytest

from a2web.settings import AppSettings
from a2web.state import (
    AppState,
    bootstrap_state_for_test,
    ensure_sqlite,
    teardown_state_for_test,
)


@pytest.mark.asyncio
async def test_ensure_sqlite_opens_once() -> None:
    state = AppState(settings=AppSettings())
    conn1 = await ensure_sqlite(state)
    conn2 = await ensure_sqlite(state)
    try:
        assert conn1 is conn2
        assert state.sqlite is conn1
    finally:
        await conn1.close()
        state.sqlite = None


@pytest.mark.asyncio
async def test_ensure_sqlite_concurrent_first_callers() -> None:
    """Two concurrent first-callers must serialize → single open."""
    state = AppState(settings=AppSettings())
    results = await asyncio.gather(ensure_sqlite(state), ensure_sqlite(state))
    try:
        assert results[0] is results[1]
    finally:
        await results[0].close()
        state.sqlite = None


@pytest.mark.asyncio
async def test_bootstrap_and_teardown_helpers() -> None:
    state = await bootstrap_state_for_test()
    assert state.sqlite is not None
    assert state.breakers is not None
    assert state.log_writer is not None
    await teardown_state_for_test(state)
    assert state.sqlite is None
