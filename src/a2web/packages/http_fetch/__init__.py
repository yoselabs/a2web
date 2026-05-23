"""http_fetch — shared HTTP transport primitive for tiers and handlers.

One callable (`fetch_bytes`) that performs every project HTTP fetch via
`curl_cffi.AsyncSession` with Chrome TLS impersonation, with proxy routing,
per-host circuit breakers, and closed-verdict error mapping. Used by
`RawTier`, `ArchiveTier`, and every site handler.

Domain-independent — boundary types (`FetchVerdict`, `FetchOutcome`) live
here; the tier / handler layers translate to the domain `Verdict` (which
adds policy verdicts the transport cannot determine).
"""

from __future__ import annotations

from .fetch import fetch_bytes
from .models import FetchOutcome, FetchVerdict

__all__ = ("FetchOutcome", "FetchVerdict", "fetch_bytes")
