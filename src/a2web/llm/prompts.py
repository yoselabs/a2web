"""a2web seam — re-exports from `packages.llm_extract.prompts`."""

from __future__ import annotations

from ..packages.llm_extract.prompts import (
    JUDGE_V1,
    TERSE_V1,
    WEBFETCH_DEFAULT_V1,
    PromptTemplate,
)

__all__ = ("JUDGE_V1", "TERSE_V1", "WEBFETCH_DEFAULT_V1", "PromptTemplate")
