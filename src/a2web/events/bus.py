"""EventBus — fan-out over anyio MemoryObjectStreams.

Each subscriber gets its own send/receive pair; `publish` iterates all
send halves. Orchestrator is the sole producer; sinks subscribe before
the fetch begins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

    from .types import Event


_DEFAULT_BUFFER = 128


class EventBus:
    """One-producer, many-subscribers bus.

    `subscribe()` allocates a fresh stream pair and returns the receive
    half; the bus retains the send half. `publish(event)` writes to every
    retained send half. With no subscribers, publish is a no-op.
    """

    __slots__ = ("_buffer", "_senders")

    def __init__(self, buffer_size: int = _DEFAULT_BUFFER) -> None:
        self._buffer = buffer_size
        self._senders: list[MemoryObjectSendStream[Event]] = []

    def subscribe(self) -> MemoryObjectReceiveStream[Event]:
        """Allocate a fresh stream pair; bus keeps the sender, returns the receiver."""
        send, recv = anyio.create_memory_object_stream(max_buffer_size=self._buffer)
        self._senders.append(send)
        return recv

    async def publish(self, event: Event) -> None:
        """Send `event` to every subscriber. No-op when no subscribers."""
        for sender in self._senders:
            await sender.send(event)

    async def aclose(self) -> None:
        """Close every retained send half; subscribers see EndOfStream."""
        for sender in self._senders:
            await sender.aclose()
        self._senders.clear()
