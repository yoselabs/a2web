"""Aggregate phase1 (tokens) + phase3 (judge scores) into results.tsv + findings.md."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
RUNS = HERE / "runs"


def main() -> None:
    p1 = {row["slug"]: row for row in json.loads((HERE / "phase1_summary.json").read_text())}
    p3 = {row["slug"]: row for row in json.loads((HERE / "phase3_summary.json").read_text())}

    rows = []
    for slug, p1r in p1.items():
        p3r = p3.get(slug, {})
        scores = p3r.get("scores", {})
        # ----- pull per-system overall + reached -----
        def s(sys_name: str, key: str) -> str:
            v = scores.get(sys_name, {})
            return str(v.get(key, "")) if isinstance(v, dict) else ""

        meta_path = RUNS / slug / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        a2 = meta.get("a2web", {})
        ft = a2.get("field_tokens", {})

        rows.append({
            "slug": slug,
            "class": p1r.get("class", ""),
            "url": p1r.get("url", ""),
            "a2web_status": a2.get("status", ""),
            "a2web_tier": a2.get("tier", ""),
            "a2web_from_browser": a2.get("from_browser", False),
            "a2web_from_archive": a2.get("from_archive", False),
            "fit_eq_content": a2.get("fit_equals_content", ""),
            # Tokens
            "tok_A_full": p1r.get("a2web_tokens_A", ""),
            "tok_B_meta": p1r.get("a2web_tokens_B", ""),
            "tok_C_content": p1r.get("a2web_tokens_C", ""),
            "tok_links": ft.get("links", 0),
            "tok_fit_md": ft.get("fit_md", 0),
            "tok_content_md": ft.get("content_md", 0),
            "tok_diagnostics": ft.get("diagnostics", 0),
            "tok_headings": ft.get("headings", 0),
            "tok_narrative": ft.get("narrative", 0),
            "links_count": a2.get("links_count", 0),
            # Judge — overall scores per system (0-5)
            "judge_wf": s("webfetch", "overall"),
            "judge_A": s("a2web_A", "overall"),
            "judge_B": s("a2web_B", "overall"),
            "judge_C": s("a2web_C", "overall"),
            # Judge — reached flags
            "reached_wf": s("webfetch", "reached"),
            "reached_A": s("a2web_A", "reached"),
            "reached_B": s("a2web_B", "reached"),
            "reached_C": s("a2web_C", "reached"),
        })

    # ---------- TSV ----------
    tsv_path = HERE / "results.tsv"
    fields = list(rows[0].keys())
    with tsv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {tsv_path}")

    # ---------- summary stats ----------
    def n(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    judge_wf = [n(r["judge_wf"]) for r in rows if n(r["judge_wf"]) is not None]
    judge_A = [n(r["judge_A"]) for r in rows if n(r["judge_A"]) is not None]
    judge_B = [n(r["judge_B"]) for r in rows if n(r["judge_B"]) is not None]
    judge_C = [n(r["judge_C"]) for r in rows if n(r["judge_C"]) is not None]

    reached_wf = sum(1 for r in rows if str(r["reached_wf"]).lower() == "true")
    reached_A = sum(1 for r in rows if str(r["reached_A"]).lower() == "true")
    reached_B = sum(1 for r in rows if str(r["reached_B"]).lower() == "true")
    reached_C = sum(1 for r in rows if str(r["reached_C"]).lower() == "true")

    tok_A = [r["tok_A_full"] for r in rows if isinstance(r["tok_A_full"], int)]
    tok_B = [r["tok_B_meta"] for r in rows if isinstance(r["tok_B_meta"], int)]
    tok_C = [r["tok_C_content"] for r in rows if isinstance(r["tok_C_content"], int)]
    tok_links = [r["tok_links"] for r in rows if isinstance(r["tok_links"], int)]
    tok_fit = [r["tok_fit_md"] for r in rows if isinstance(r["tok_fit_md"], int)]

    print("\n=== headline numbers ===")
    print(f"Reached (judge said real content delivered):")
    print(f"  WebFetch : {reached_wf}/20")
    print(f"  a2web A  : {reached_A}/20")
    print(f"  a2web B  : {reached_B}/20")
    print(f"  a2web C  : {reached_C}/20")
    print(f"\nMean judge score (0-5) over ALL urls:")
    if judge_wf: print(f"  WebFetch : {statistics.mean(judge_wf):.2f}  (median {statistics.median(judge_wf):.1f})")
    if judge_A:  print(f"  a2web A  : {statistics.mean(judge_A):.2f}  (median {statistics.median(judge_A):.1f})")
    if judge_B:  print(f"  a2web B  : {statistics.mean(judge_B):.2f}  (median {statistics.median(judge_B):.1f})")
    if judge_C:  print(f"  a2web C  : {statistics.mean(judge_C):.2f}  (median {statistics.median(judge_C):.1f})")

    print(f"\nMean a2web payload tokens:")
    print(f"  A_full           : {statistics.mean(tok_A):.0f}  (sum {sum(tok_A)})")
    print(f"  B_meta           : {statistics.mean(tok_B):.0f}  (sum {sum(tok_B)})")
    print(f"  C_content_only   : {statistics.mean(tok_C):.0f}  (sum {sum(tok_C)})")
    print(f"  ratio A/C        : {sum(tok_A)/max(sum(tok_C),1):.2f}x")
    print(f"  ratio A/B        : {sum(tok_A)/max(sum(tok_B),1):.2f}x")
    print(f"\nLinks field tokens (across 20 urls): sum={sum(tok_links)}  mean={statistics.mean(tok_links):.0f}  max={max(tok_links)}")
    print(f"fit_md field tokens (across 20 urls): sum={sum(tok_fit)}    mean={statistics.mean(tok_fit):.0f}  max={max(tok_fit)}")

    fit_dupes = sum(1 for r in rows if r["fit_eq_content"] is True)
    print(f"\nfit_md == content_md (pure duplicate tax): {fit_dupes}/20 fetches")

    # By-URL paired comparison: a2web A vs C delta
    pair_rows = [(r["slug"], n(r["judge_A"]), n(r["judge_C"]), r["tok_A_full"], r["tok_C_content"]) for r in rows]
    deltas = [(s, a, c, ta, tc) for s, a, c, ta, tc in pair_rows if a is not None and c is not None and isinstance(ta, int) and isinstance(tc, int)]
    same_or_better_C = sum(1 for s, a, c, ta, tc in deltas if c >= a)
    print(f"\nC scored >= A on {same_or_better_C}/{len(deltas)} URLs (H1: links/extras are tax)")

    saved = [(ta - tc) for s, a, c, ta, tc in deltas]
    print(f"Median tokens saved by going A→C: {statistics.median(saved):.0f}")
    print(f"Median % saved: {statistics.median([(ta-tc)/ta*100 for s,a,c,ta,tc in deltas]):.1f}%")


if __name__ == "__main__":
    main()
