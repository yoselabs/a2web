"""Eval system manifests.

The eval harness needs richer construction context than just `AppSettings`
(provider instance + bench state + Resources bundle). Each factory here
accepts the `EvalSystemContext` struct defined below; `load_surface` treats
it opaquely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...packages.llm_extract import Provider
    from ...state import AppState, Resources


@dataclass(frozen=True, slots=True)
class EvalSystemContext:
    """Per-factory construction context for the eval-systems surface."""

    provider: Provider
    state: AppState
    resources: Resources
