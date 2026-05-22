"""Shared test fixture data.

`FIXTURES_DIR` is the stable anchor for the fixture directory. Test files
import it instead of recomputing `Path(__file__).parent / "fixtures"`, so a
test resolves its fixtures correctly regardless of how deep it sits in the
`tests/` tree.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
