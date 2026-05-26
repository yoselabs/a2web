"""A2WebDetail manifest — runs the production a2web pipeline as an eval system."""

from __future__ import annotations

from a2web._manifests.eval_systems import EvalSystemContext
from a2web._plugin import PluginManifest, Unavailable
from a2web.llm_eval.systems import A2WebDetail, EvalSystem


def _build(ctx: EvalSystemContext) -> EvalSystem | Unavailable:
    return A2WebDetail(state=ctx.state, resources=ctx.resources)


MANIFEST = PluginManifest(
    name="a2web_detail",
    protocol=EvalSystem,
    factory=_build,
)
