"""Minimal repro for the bench shutdown-thread-leak (BACKLOG.md:111).

Run with: `uv run python scripts/spike_shutdown_leak.py`

If the process hangs for >5s after "main returned" prints, confirms the leak.
Adds a SIGALRM watchdog that dumps every non-daemon thread's stack so the
output names the parked thread (expecting "AnyIO worker thread" parked in
`Queue.get` from `anyio._backends._asyncio.WorkerThread.run`).
"""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
import traceback


async def _hit_claude_code_once() -> None:
    """Drive one query() through claude-agent-sdk. Tools off, max_turns=1."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        ThinkingConfigDisabled,
        TextBlock,
        query,
    )

    options = ClaudeAgentOptions(
        model="claude-haiku-4-5",
        tools=[],
        max_turns=1,
        max_thinking_tokens=0,
        system_prompt="",
        setting_sources=[],
        skills=[],
        extra_args={"disable-slash-commands": None},
        mcp_servers={},
        strict_mcp_config=True,
        agents={},
        thinking=ThinkingConfigDisabled(type="disabled"),
    )

    parts: list[str] = []
    result_msg = None
    async for msg in query(prompt="say 'hi' and nothing else", options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(msg, ResultMessage):
            result_msg = msg  # production iteration shape — full drain

    print(f"  reply: {''.join(parts)[:40]!r} (result={result_msg is not None})")


async def _amain() -> None:
    print("calling claude-agent-sdk x 3 concurrent (mirrors bench concurrency=4)")
    await asyncio.gather(*(_hit_claude_code_once() for _ in range(3)))
    print("returning from _amain")


def _watchdog(signum: int, frame) -> None:  # noqa: ANN001 - signal handler
    print("\n=== WATCHDOG FIRED (5s after main exit) ===", file=sys.stderr)
    for t in threading.enumerate():
        if t.daemon or t is threading.main_thread():
            continue
        print(f"\nThread {t.name!r} (daemon={t.daemon}, alive={t.is_alive()}):", file=sys.stderr)
        frame = sys._current_frames().get(t.ident)
        if frame is not None:
            traceback.print_stack(frame, file=sys.stderr)
    print("\n=== forcing exit ===", file=sys.stderr)
    import os
    os._exit(99)


def main() -> int:
    asyncio.run(_amain())
    print("main returned — arming 5s watchdog; if leak present we'll dump stacks")
    signal.signal(signal.SIGALRM, _watchdog)
    signal.alarm(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
