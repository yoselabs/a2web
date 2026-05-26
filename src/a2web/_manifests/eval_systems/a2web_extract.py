"""A2WebExtract manifest — extraction-only variant of the a2web system."""

from __future__ import annotations

from a2web._manifests.eval_systems import EvalSystemContext
from a2web._plugin import PluginManifest, Unavailable
from a2web.llm_eval.systems import A2WebExtract, EvalSystem


def _build(ctx: EvalSystemContext) -> EvalSystem | Unavailable:
    return A2WebExtract(state=ctx.state, resources=ctx.resources)


MANIFEST = PluginManifest(
    name="a2web_extract",
    protocol=EvalSystem,
    factory=_build,
)
