"""LLM-backed content extraction + LLM-as-judge — in-tree microsofware.

Pure primitives for running prompts against a Provider (Anthropic,
Claude Code OS session, OpenRouter, Ollama) over arbitrary content +
caching the result. Zero `a2web.<domain>` imports.

Boundary types are package-owned: `Provider` Protocol, `ModelSpec`,
`ExtractionResult`, `ExtractionCache`, `PromptTemplate`, `Judge`,
`JudgeVerdict`, `RouterPayload`, `NextUrlBoundary`. Domain wiring
(AppSettings provider selection, SqliteResource cache plumbing) lives at
the a2web seam in `a2web.llm.resource`.
"""

from __future__ import annotations

from .cache import ExtractionCache, ExtractionCacheRow, hash_text
from .errors import LLMNotAvailable
from .extractor import ExtractionResult, Extractor, LlmNextLink, ModelSpec
from .judge import Judge, JudgeParseError, JudgeVerdict
from .prompts import (
    EXTRACT_CACHEABLE_V1,
    EXTRACT_ROUTER_V1,
    JUDGE_V1,
    TERSE_V1,
    WEBFETCH_DEFAULT_V1,
    PromptParts,
    PromptTemplate,
)
from .providers import Provider, ProviderResponse
from .router_payload import NextUrlBoundary, RouterPayload
from .wobble import (
    ParseError,
    Wobbled,
    WobblePolicy,
    WobbleSkip,
    WobbleTolerance,
    parse_list_with_policy,
    parse_with_policy,
    recovered_fields,
    unwrap,
)

__all__ = [
    "EXTRACT_CACHEABLE_V1",
    "EXTRACT_ROUTER_V1",
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
    "LlmNextLink",
    "ModelSpec",
    "NextUrlBoundary",
    "ParseError",
    "PromptParts",
    "PromptTemplate",
    "Provider",
    "ProviderResponse",
    "RouterPayload",
    "WobblePolicy",
    "WobbleSkip",
    "WobbleTolerance",
    "Wobbled",
    "hash_text",
    "parse_list_with_policy",
    "parse_with_policy",
    "recovered_fields",
    "unwrap",
]
