"""a2web.llm — optional LLM-backed extraction + evaluation.

Gated behind the `[llm]` install extra. Importing this module without the
extra installed succeeds; attempting to actually invoke an extractor raises
`LLMNotAvailable` with an actionable message.

Public surface:
- `Extractor` — wraps a Provider + PromptTemplate, exposes `extract(content, ask)`.
- `ModelSpec` — `(provider_name, model_id)` tuple identifying the LLM to call.
- `PromptTemplate` — frozen, versioned template (see prompts.py).
- `Provider` — Protocol for completion backends (anthropic, openrouter, …).
- `LLMNotAvailable` — raised when an LLM call is attempted without the extra.

Wired into `routers.fetch` via the optional `ask=` parameter (v0.4). When
`ask` is unset, this module is never imported.
"""

from __future__ import annotations

from .cache import ExtractionCache, ExtractionCacheRow, hash_text
from .errors import LLMNotAvailable
from .extractor import ExtractionResult, Extractor, ModelSpec
from .judge import Judge, JudgeParseError, JudgeVerdict
from .prompts import (
    JUDGE_V1,
    TERSE_V1,
    WEBFETCH_DEFAULT_V1,
    PromptTemplate,
)
from .providers import Provider, ProviderResponse

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
