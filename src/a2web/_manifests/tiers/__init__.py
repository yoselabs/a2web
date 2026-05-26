"""Tier manifests. Each plugin returns a no-arg `Tier` instance; priority
mirrors `TIER_ORDER` (descending). `priority=-1` marks out-of-band tiers
(`archive`, `browser`) that the orchestrator dispatches via the playbook
rather than via the main tier loop."""

from __future__ import annotations
