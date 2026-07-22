"""The test harness daemonizes aiosqlite worker threads.

aiosqlite >=0.21 creates its per-connection worker thread as a *non-daemon*
thread (an upstream change made for write-durability). A `SqliteResource`
opened by a test that does not run through the full lifecycle — FastMCP's
`lifespan=` exit, which calls `Components.aclose()` — is never explicitly
closed, so its worker thread parks on an empty queue forever and
`threading._shutdown()` hangs the interpreter at process exit.
`tests/conftest.py` patches `aiosqlite` so the worker thread is a daemon in the
test process; test databases are throwaway temp / in-memory files with no
exit-durability need. This test guards that patch.

**This is not a test-only hazard, and the sunset proved it.** The same
non-daemon thread hung the *real* CLI in Phase 5: the first working version of
`a2web web query` printed correct JSON and then never exited, because the
command did not unwind its `ResourceScope`. In production the daemon patch is
absent by design — durability matters there — so closing the scope is the only
thing that lets the process end. See `cli._make_command`, which does it in a
`finally`.
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
