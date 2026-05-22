"""The test harness daemonizes aiosqlite worker threads.

aiosqlite >=0.21 creates its per-connection worker thread as a *non-daemon*
thread (an upstream change made for write-durability). A `SqliteResource`
opened by a test that does not run through the a2kit `async with app:`
lifecycle is never explicitly closed, so its worker thread parks on an empty
queue forever and `threading._shutdown()` hangs the interpreter at process
exit. `tests/conftest.py` patches `aiosqlite` so the worker thread is a
daemon in the test process; test databases are throwaway temp / in-memory
files with no exit-durability need. This test guards that patch.
"""

from __future__ import annotations

import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_aiosqlite_worker_thread_is_daemon() -> None:
    conn = await aiosqlite.connect(":memory:")
    try:
        assert conn._thread.daemon is True, (
            "aiosqlite worker thread is non-daemon — conftest's daemonize patch "
            "is missing; an unclosed test connection will hang interpreter shutdown"
        )
    finally:
        await conn.close()
