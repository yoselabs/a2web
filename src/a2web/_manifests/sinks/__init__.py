"""LDD sink manifests.

Sinks are async callables `(LddEmission) -> None` registered via
`app.ldd.add_sink(...)`. Each manifest returns the callable; the boot path
collects them and feeds them into a2kit one by one.

LiveSink (bench-only) is NOT a manifest — it needs a per-run `total=` arg
that the factory can't know about. It stays as direct construction in
`llm_eval/__main__.py`.
"""

from __future__ import annotations

from a2kit.packages.ldd import LddSink as Sink

__all__ = ("Sink",)
