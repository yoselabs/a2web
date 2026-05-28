"""a2web vs WebFetch benchmark runner.

Phase 1: fetch each corpus URL via a2web, persist raw response, build three
variants (A_full / B_meta / C_content_only), and count tokens per field.

Phase 2 (separate driver): the Claude Code session calls WebFetch for each URL
and saves the result to runs/<slug>/webfetch.txt.

Phase 3 (judge.py): feed each variant + WebFetch answer through a reader, then
score against criteria.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import tiktoken
import yaml

HERE = Path(__file__).parent
CORPUS = HERE / "corpus.yaml"
RUNS = HERE / "runs"
ENC = tiktoken.get_encoding("cl100k_base")


def tok(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(ENC.encode(value))
    return len(ENC.encode(json.dumps(value, ensure_ascii=False)))


def fetch_a2web(url: str, timeout: int = 120) -> tuple[dict[str, Any] | None, str, int]:
    """Run `a2web web fetch --url=... --format=json`. Return (response, stderr, wall_ms)."""
    t0 = time.time()
    proc = subprocess.run(
        ["uv", "run", "a2web", "--no-events", "web", "fetch", "--url", url, "--format", "json"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    wall_ms = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        return None, proc.stderr, wall_ms
    # Output may include LDD event lines + final JSON; take the last non-empty line.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return None, proc.stderr or "empty stdout", wall_ms
    try:
        resp = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        return None, f"json decode error: {e}\nlast line: {lines[-1][:200]}", wall_ms
    return resp, proc.stderr, wall_ms


def build_variants(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build A_full, B_meta, C_content_only views of the response."""
    a_full = dict(resp)
    b_meta = {
        "url": resp.get("url"),
        "title": resp.get("title"),
        "byline": resp.get("byline"),
        "published": resp.get("published"),
        "content_md": resp.get("content_md"),
    }
    c_content = {"content_md": resp.get("content_md")}
    return {"A_full": a_full, "B_meta": b_meta, "C_content_only": c_content}


def field_breakdown(resp: dict[str, Any]) -> dict[str, int]:
    """Per-field token counts on the full a2web response."""
    fields = [
        "content_md",
        "fit_md",
        "title",
        "byline",
        "published",
        "narrative",
        "links",
        "headings",
        "diagnostics",
        "operator_hints",
        "meta",
        "tokens",
        "url",
        "status",
        "tier",
        "confidence",
        "cache",
        "total_ms",
        "started_at",
    ]
    out = {}
    for f in fields:
        if f in resp:
            out[f] = tok(resp[f])
    return out


def main() -> int:
    corpus = yaml.safe_load(CORPUS.read_text())
    RUNS.mkdir(parents=True, exist_ok=True)
    summary_rows = []

    for entry in corpus["urls"]:
        slug = entry["slug"]
        url = entry["url"]
        print(f"\n=== [{slug}] {url}")
        run_dir = RUNS / slug
        run_dir.mkdir(parents=True, exist_ok=True)

        # Persist the entry for downstream tools.
        (run_dir / "entry.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))

        resp, stderr, wall_ms = fetch_a2web(url)
        if resp is None:
            print(f"  ! a2web fetch FAILED in {wall_ms}ms")
            (run_dir / "a2web_error.txt").write_text(stderr or "")
            summary_rows.append(
                {
                    "slug": slug,
                    "class": entry["class"],
                    "url": url,
                    "a2web_status": "exec_error",
                    "a2web_wall_ms": wall_ms,
                }
            )
            continue

        # Persist raw + variants + breakdown.
        (run_dir / "a2web_raw.json").write_text(json.dumps(resp, indent=2, ensure_ascii=False))
        variants = build_variants(resp)
        for vname, vdata in variants.items():
            (run_dir / f"a2web_{vname}.json").write_text(json.dumps(vdata, indent=2, ensure_ascii=False))

        # Token math.
        variant_tokens = {vname: tok(json.dumps(vdata, ensure_ascii=False)) for vname, vdata in variants.items()}
        breakdown = field_breakdown(resp)
        meta = {
            "slug": slug,
            "class": entry["class"],
            "url": url,
            "a2web": {
                "status": resp.get("status"),
                "tier": resp.get("tier"),
                "verdict": resp.get("confidence"),
                "wall_ms_cli": wall_ms,
                "wall_ms_internal": resp.get("total_ms"),
                "from_archive": any(d.get("step") == "archive" for d in resp.get("diagnostics", [])),
                "from_browser": any(d.get("step") == "browser" for d in resp.get("diagnostics", [])),
                "field_tokens": breakdown,
                "variant_tokens": variant_tokens,
                "links_count": len(resp.get("links") or []),
                "headings_count": len(resp.get("headings") or []),
                "content_chars": len(resp.get("content_md") or ""),
                "fit_equals_content": (resp.get("fit_md") == resp.get("content_md")),
            },
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        summary_rows.append(
            {
                "slug": slug,
                "class": entry["class"],
                "url": url,
                **{f"a2web_{k}": v for k, v in meta["a2web"].items() if not isinstance(v, dict)},
                "a2web_tokens_A": variant_tokens["A_full"],
                "a2web_tokens_B": variant_tokens["B_meta"],
                "a2web_tokens_C": variant_tokens["C_content_only"],
            }
        )
        print(
            f"  ok status={resp.get('status')} tier={resp.get('tier')} "
            f"wall={wall_ms}ms tokens A={variant_tokens['A_full']} "
            f"B={variant_tokens['B_meta']} C={variant_tokens['C_content_only']} "
            f"links={len(resp.get('links') or [])}"
        )

    (HERE / "phase1_summary.json").write_text(json.dumps(summary_rows, indent=2, ensure_ascii=False))
    print(f"\nWrote phase1 summary with {len(summary_rows)} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
