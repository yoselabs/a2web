"""Provider backends for a2web.llm.

`base.py` defines the Provider Protocol + ProviderResponse dataclass.
`anthropic.py` is the v0.4 reference implementation (Haiku/Sonnet).
`openrouter.py` lands in v0.5.
"""

from __future__ import annotations

from .base import Provider, ProviderResponse

__all__ = ["Provider", "ProviderResponse"]
