"""OTel sink manifest. Returns Unavailable when the OpenTelemetry SDK is
absent — the registry drops it before `app.ldd.add_sink(...)` ever sees it."""

from __future__ import annotations

from a2web._manifests.sinks import Sink
from a2web._plugin import PluginManifest, Unavailable
from a2web.events.sinks import _TRACER, otel_sink
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Sink | Unavailable:
    if _TRACER is None:
        return Unavailable("opentelemetry sdk not installed")
    return otel_sink


MANIFEST = PluginManifest(
    name="otel",
    protocol=Sink,
    factory=_build,
)
