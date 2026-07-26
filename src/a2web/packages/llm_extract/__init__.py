"""LLM-backed content extraction + LLM-as-judge — in-tree microsofware.

Pure primitives for running prompts against a Provider (Anthropic,
Claude Code OS session, OpenRouter, Ollama) over arbitrary content +
caching the result. Zero `a2web.<domain>` imports.

Boundary types are package-owned: `Provider` Protocol, `ModelSpec`,
`ExtractionResult`, `PromptTemplate`, `Judge`, `JudgeVerdict`,
`RouterPayload`, `OtherPageBoundary`. The completion cache (`LlmCache`) is the
shelf `llm-cache` package, re-exported here. Domain wiring (AppSettings provider
selection, SqliteResource cache plumbing) lives at the a2web seam in
`a2web.llm.resource`.
"""

from __future__ import annotations

# Provider contract adopted from the shelf (anyllm) — `Provider` is anyllm's
# `LLMProvider` Protocol, `ProviderResponse` is its `Completion` (identical
# fields). Re-exported under a2web's historical names so package consumers and
# tests keep importing them from `llm_extract` unchanged.
from anyllm import Completion as ProviderResponse
from anyllm import LLMProvider as Provider

# The completion cache was promoted to the shelf (llm-cache 2026-07-26). It
# speaks anyllm.Completion and keys on an opaque (key, model); a2web builds the
# composite key from content+ask+template via `make_key`. Re-exported so the
# package's consumers import it from `llm_extract` unchanged.
from llm_cache import LlmCache, hash_text, make_key

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
from .router_payload import OtherPageBoundary, RouterPayload
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
    "ExtractionResult",
    "Extractor",
    "Judge",
    "JudgeParseError",
    "JudgeVerdict",
    "LLMNotAvailable",
    "LlmCache",
    "LlmNextLink",
    "ModelSpec",
    "OtherPageBoundary",
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
    "make_key",
    "parse_list_with_policy",
    "parse_with_policy",
    "recovered_fields",
    "unwrap",
]
