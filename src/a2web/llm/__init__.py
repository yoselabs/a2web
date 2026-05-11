"""a2web.llm — seam over `packages.llm_extract`.

The extraction + judge primitives + providers live in
`a2web.packages.llm_extract` (in-tree microsofware, zero a2web-domain
imports). This module is the a2web seam: it re-exports the package's
public surface so callers (and the optional `[llm]` install extra)
keep their existing import paths.

The domain-coupled wiring lives in `a2web.llm.resource`
(`LlmExtractorResource` — constructs an `Extractor` from `AppSettings`
+ `SqliteResource` with provider auto/fallback).
"""

from __future__ import annotations

from ..packages.llm_extract import (
    JUDGE_V1,
    TERSE_V1,
    WEBFETCH_DEFAULT_V1,
    ExtractionCache,
    ExtractionCacheRow,
    ExtractionResult,
    Extractor,
    Judge,
    JudgeParseError,
    JudgeVerdict,
    LLMNotAvailable,
    ModelSpec,
    PromptTemplate,
    Provider,
    ProviderResponse,
    hash_text,
)

__all__ = [
    "JUDGE_V1",
    "TERSE_V1",
    "WEBFETCH_DEFAULT_V1",
    "ExtractionCache",
    "ExtractionCacheRow",
    "ExtractionResult",
    "Extractor",
    "Judge",
    "JudgeParseError",
    "JudgeVerdict",
    "LLMNotAvailable",
    "ModelSpec",
    "PromptTemplate",
    "Provider",
    "ProviderResponse",
    "hash_text",
]
