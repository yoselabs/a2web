"""WebFetchBaseline manifest — Claude Code's WebFetch reproduction."""

from __future__ import annotations

from plugin_surface import PluginManifest, Unavailable

from a2web._manifests.eval_systems import EvalSystemContext
from a2web.llm_eval.systems import EvalSystem, WebFetchBaseline


def _build(ctx: EvalSystemContext) -> EvalSystem | Unavailable:
    return WebFetchBaseline(provider=ctx.provider)


MANIFEST = PluginManifest(
    name="webfetch_baseline",
    protocol=EvalSystem,
    factory=_build,
)
