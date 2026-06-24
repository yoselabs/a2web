"""Log sink manifests.

Sinks are stdlib `logging.Handler`s registered via
`app.log.add_handler(...)`. Each manifest returns a handler instance; the
boot path collects them and attaches them one by one.

LiveSink (bench-only) is NOT a manifest — it needs a per-run `total=` arg
that the factory can't know about. It stays as direct construction in
`llm_eval/__main__.py`.
"""

from __future__ import annotations

from logging import Handler as Sink

__all__ = ("Sink",)
