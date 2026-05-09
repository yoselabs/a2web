"""Size-based rotation with gzip on rollover. Daily filename prefix."""

from __future__ import annotations

import gzip
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ROTATION_BYTES = 16 * 1024 * 1024

_ROLLED_NAME_RE = re.compile(r"^fetches-(\d{4}-\d{2}-\d{2})-(\d{2})\.ndjson(?:\.gz)?$")


def next_rolled_path(active: Path, *, now: datetime | None = None) -> Path:
    """Pick the next `fetches-YYYY-MM-DD-NN.ndjson` slot for rollover.

    Scans the directory for existing rolled files (gzipped or not) with
    today's date stamp and returns the next zero-padded sequence number.
    """
    moment = now or datetime.now(UTC)
    date_stamp = moment.strftime("%Y-%m-%d")
    parent = active.parent
    used_seqs: set[int] = set()
    if parent.is_dir():
        for entry in parent.iterdir():
            match = _ROLLED_NAME_RE.match(entry.name)
            if match and match.group(1) == date_stamp:
                used_seqs.add(int(match.group(2)))
    next_seq = max(used_seqs, default=0) + 1
    return parent / f"fetches-{date_stamp}-{next_seq:02d}.ndjson"


def gzip_file(src: Path) -> Path:
    """Gzip `src` to `src + ".gz"` and remove the original. Returns the gz path."""
    dst = src.with_suffix(src.suffix + ".gz")
    with src.open("rb") as fin, gzip.open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    src.unlink()
    return dst
