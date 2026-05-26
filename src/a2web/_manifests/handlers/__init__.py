"""Site-handler manifests.

Each handler is a no-arg constructor; the factory ignores `_settings`.
Dispatch order matters: specific URL-pattern handlers run before
config-driven ones (DiscourseHandler) that could overlap. Priority values
mirror the original `_HANDLERS` tuple order — higher fires first.
"""

from __future__ import annotations
